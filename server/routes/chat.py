"""
调度员 - 聊天智能体 API 路由
轻量 LLM 调度代理：听懂用户需求 → 调 Task Dispatcher API 分派 → 回报
持久化存储，支持多智能体切换对话
"""
from __future__ import annotations

import json
import os
import httpx
from typing import Optional
from fastapi import APIRouter, HTTPException

from models import Task, TaskLog

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 全局引用，在 dispatcher.py 中注入
config: dict = None  # type: ignore
storage: object = None  # type: ignore
dispatcher_core: object = None  # type: ignore
mesh_client: object = None  # type: ignore
mesh_remote_client: object = None  # type: ignore

# MESH ID 映射（本地ID → 远程MESH上的实际ID）
AGENT_ID_MAP = {
    "xiao-lan": "xiaolan",
    "xiao-bai": "xiaobai",
    "xiao-qing": "xiaoqing",
    "xiao-hei": "xiaohei",
}

# ==================== MiMo LLM 客户端 ====================

_llm_client: Optional[httpx.AsyncClient] = None
_llm_config: dict = {}
_tools: list[dict] = []


def _load_llm_config():
    """从 config 加载 LLM 配置"""
    global _llm_config
    agent_cfg = config.get("dispatcher_agent", {})
    llm_cfg = agent_cfg.get("llm", {})
    key_path = llm_cfg.get("api_key_path", "")
    api_key = llm_cfg.get("api_key", "")

    if key_path:
        expanded = os.path.expanduser(key_path)
        if os.path.exists(expanded):
            with open(expanded, "r") as f:
                api_key = f.read().strip()

    _llm_config = {
        "base_url": llm_cfg.get("base_url", "https://api.xiaomimimo.com/v1"),
        "api_key": api_key,
        "model": llm_cfg.get("model", "mimo-v2-omni"),
        "max_tokens": llm_cfg.get("max_tokens", 2048),
        "temperature": llm_cfg.get("temperature", 0.7),
    }


async def _get_llm_client() -> httpx.AsyncClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = httpx.AsyncClient(timeout=60)
    return _llm_client


def _get_tools() -> list[dict]:
    """获取 function calling 工具定义"""
    if _tools:
        return _tools

    _tools.append({
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "创建新任务并自动分派给合适的智能体",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "任务标题"},
                    "description": {"type": "string", "description": "任务详细描述"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "required_skills": {"type": "string", "description": "所需能力，逗号分隔"},
                },
                "required": ["title", "description"],
            },
        },
    })
    _tools.append({
        "type": "function",
        "function": {
            "name": "get_task_status",
            "description": "获取任务状态和进度",
            "parameters": {"type": "object", "properties": {
                "task_id": {"type": "string"},
            }, "required": ["task_id"]},
        },
    })
    _tools.append({
        "type": "function",
        "function": {
            "name": "list_agents",
            "description": "获取可用智能体列表",
            "parameters": {"type": "object", "properties": {}},
        },
    })
    _tools.append({
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "查询记忆系统，获取各智能体的职责分工和任务分配规则。当不确定任务该分给谁时先查记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，如'磁盘''网站''安全'"},
                },
                "required": ["query"],
            },
        },
    })
    return _tools


def _get_system_prompt(agent_id: str = "dispatcher") -> str:
    """获取系统 prompt，可按智能体不同返回不同 prompt"""
    agent_cfg = config.get("dispatcher_agent", {})
    agent_prompts = agent_cfg.get("agent_prompts", {})
    if agent_id in agent_prompts:
        return agent_prompts[agent_id]
    return agent_cfg.get("system_prompt", "你是「调度员」，一个任务调度智能体。听懂用户的请求，创建任务并跟踪进度。")


def _format_history_for_agent(history_rows: list[dict], current_message: str) -> str:
    """把最近20轮对话格式化成上下文，通过MESH转发给智能体"""
    parts = []
    for r in history_rows:
        role = r.get("role", "")
        content = r.get("content", "")
        if role == "system" or role == "tool" or not content:
            continue
        label = "用户" if role == "user" else "你"
        parts.append(f"{label}: {content}")
    # 只取最近20条 + 当前消息
    recent = parts[-20:] if len(parts) > 20 else parts
    recent.append(f"用户: {current_message}")
    return "\n".join(recent)


# ==================== Function 执行器 ====================

async def _execute_function(name: str, args: dict) -> dict:
    port = config.get("server", {}).get("port", 8767)

    if name == "create_task":
        title = args.get("title", "未命名任务")
        desc = args.get("description", "")
        priority = args.get("priority", "medium")
        skills = args.get("required_skills", "")

        task = Task(title=title, description=desc, priority=priority, required_skills=skills)
        created = await storage.create_task(task)
        await storage.add_log(TaskLog(
            task_id=created.id, action="created",
            details=f"调度员创建任务：{title}",
        ))
        dispatched = await dispatcher_core.auto_dispatch(created)
        return {
            "task_id": dispatched.id, "title": dispatched.title,
            "status": dispatched.status,
            "assigned_to": dispatched.assigned_to or "未分配",
            "message": f"任务已创建（ID: {dispatched.id}），状态：{dispatched.status}",
        }

    elif name == "get_task_status":
        task_id = args.get("task_id", "")
        result = await dispatcher_core.track_progress(task_id)
        return result if "error" not in result else {"error": result["error"]}

    elif name == "list_agents":
        agents = await storage.get_agents()
        return {"agents": [
            {"id": a.id, "name": a.name, "status": a.status,
             "capabilities": a.capabilities,
             "current_load": a.current_load, "max_load": a.max_load}
            for a in agents
        ]}

    elif name == "search_memory":
        query = args.get("query", "")
        if not query:
            return {"results": []}
        results = await storage.search_memory(query)
        return {"results": [
            {"key": r["key"], "value": r["value"], "category": r["category"]}
            for r in results
        ]}

    return {"error": f"未知 function: {name}"}


# ==================== LLM 调用 ====================

async def _call_llm(messages: list[dict], agent_id: str = "dispatcher") -> dict:
    client = await _get_llm_client()
    _load_llm_config()

    body = {
        "model": _llm_config["model"],
        "messages": messages,
        "max_tokens": _llm_config["max_tokens"],
        "temperature": _llm_config["temperature"],
        "tools": _get_tools(),
        "tool_choice": "auto",
    }

    resp = await client.post(
        f"{_llm_config['base_url']}/chat/completions",
        headers={
            "Authorization": f"Bearer {_llm_config['api_key']}",
            "Content-Type": "application/json",
        },
        json=body,
    )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {resp.status_code}")

    return resp.json()


# ==================== 持久化历史管理 ====================


async def _load_history(session_id: str, agent_id: str = "dispatcher") -> list[dict]:
    """从数据库加载历史，如果为空则插入 system prompt"""
    rows = await storage.get_chat_history(session_id)
    if not rows:
        # 新会话，写入 system prompt
        system_content = _get_system_prompt(agent_id)
        await storage.save_chat_message(session_id, "system", system_content)
        return [{"role": "system", "content": system_content}]

    # 转换 DB 行 → LLM messages
    messages = []
    for r in rows:
        role = r["role"]
        msg = {"role": role}
        if role == "tool":
            msg["tool_call_id"] = r["tool_call_id"]
            msg["content"] = r["content"]
        elif role == "assistant":
            msg["content"] = r.get("content") or ""
            if r.get("tool_calls"):
                msg["tool_calls"] = r["tool_calls"]
        else:
            msg["content"] = r.get("content") or ""
        messages.append(msg)

    # 确保第一条是 system
    if not messages or messages[0]["role"] != "system":
        system_content = _get_system_prompt(agent_id)
        messages.insert(0, {"role": "system", "content": system_content})

    return messages


async def _save_message(session_id: str, role: str, content: str,
                         tool_calls: list = None, tool_call_id: str = None):
    """保存消息到数据库"""
    tc_str = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
    await storage.save_chat_message(session_id, role, content or "",
                                     tool_calls=tc_str, tool_call_id=tool_call_id)


# ==================== API 路由 ====================


@router.post("")
async def chat(request: dict):
    """
    聊天接口：接收用户消息 → LLM → function calling → 回复
    支持 agent_id 参数来切换不同智能体
    """
    try:
        message = request.get("message", "").strip()
        session_id = request.get("session_id", "default")
        agent_id = request.get("agent_id", "dispatcher")

        if not message:
            return {"code": 1, "message": "消息不能为空"}

        # 非调度员智能体：通过 MESH 转发给真实智能体（带上对话历史）
        if agent_id != "dispatcher":
            client = mesh_client
            if client:
                try:
                    # 加载历史上下文
                    history_rows = await storage.get_chat_history(session_id)
                    context = _format_history_for_agent(history_rows, message)
                    await _save_message(session_id, "user", message)
                    # 映射ID（远程MESH可能用不同命名）
                    target_id = AGENT_ID_MAP.get(agent_id, agent_id)
                    reply = await client.send_to_agent(target_id, context, timeout=60)
                    if reply:
                        await _save_message(session_id, "assistant", reply)
                        return {"code": 0, "data": {"reply": reply, "session_id": session_id, "agent_id": agent_id}}
                    else:
                        fallback = f"⚠️ 智能体 {agent_id} 未回复（可能不在线）"
                        await _save_message(session_id, "assistant", fallback)
                        return {"code": 0, "data": {"reply": fallback, "session_id": session_id, "agent_id": agent_id}}
                except Exception as e:
                    return {"code": 1, "message": f"MESH 转发失败: {e}"}
            else:
                fallback = f"⚠️ 无法连接 {agent_id} 所在的 MESH"
                return {"code": 0, "data": {"reply": fallback, "session_id": session_id, "agent_id": agent_id}}

        # 调度员：走 MiMo LLM
        # 加载历史 + 追加用户消息
        history = await _load_history(session_id, agent_id)
        history.append({"role": "user", "content": message})
        await _save_message(session_id, "user", message)

        # LLM 调用循环（多轮 function calling）
        max_rounds = 5
        for _round in range(max_rounds):
            llm_response = await _call_llm(history)
            choice = llm_response.get("choices", [{}])[0]
            msg = choice.get("message", {})

            if not msg:
                raise HTTPException(status_code=502, detail="LLM 返回为空")

            tool_calls = msg.get("tool_calls", [])

            if not tool_calls:
                reply = msg.get("content", "好的，已处理完成。")
                await _save_message(session_id, "assistant", reply)
                return {
                    "code": 0,
                    "data": {"reply": reply, "session_id": session_id, "agent_id": agent_id},
                }

            # 有 tool_calls：保存 assistant 消息（含 tool_calls）→ 执行 → 保存 tool 结果
            history.append({
                "role": "assistant",
                "content": msg.get("content", ""),
                "tool_calls": tool_calls,
            })
            await _save_message(session_id, "assistant", msg.get("content", ""),
                                 tool_calls=tool_calls)

            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                func_args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    func_args = json.loads(func_args_str)
                except json.JSONDecodeError:
                    func_args = {}

                result = await _execute_function(func_name, func_args)
                result_str = json.dumps(result, ensure_ascii=False)
                history.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result_str})
                await _save_message(session_id, "tool", result_str,
                                     tool_call_id=tc.get("id", ""))

        return {
            "code": 0,
            "data": {"reply": "处理步骤较多，已经在执行中，请稍后查看任务状态。",
                     "session_id": session_id, "agent_id": agent_id},
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str = "default"):
    """获取聊天历史（过滤掉 system 消息，简化工具有用信息）"""
    try:
        rows = await storage.get_chat_history(session_id)
        clean = []
        for r in rows:
            if r["role"] == "system":
                continue
            item = {"role": r["role"], "content": r.get("content", "")}
            item["timestamp"] = r.get("timestamp", "")
            if r["role"] not in ("tool",) and not (r["role"] == "assistant" and not r.get("content")):
                clean.append(item)
        return {"code": 0, "data": {"session_id": session_id, "messages": clean}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions():
    """获取所有会话列表"""
    try:
        sessions = await storage.get_sessions()
        result = []
        for s in sessions:
            sid = s["session_id"]
            title = await storage.get_session_title(sid)
            result.append({
                "session_id": sid,
                "title": title,
                "last_time": s.get("last_time", ""),
            })
        return {"code": 0, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    try:
        await storage.delete_session(session_id)
        return {"code": 0, "message": "已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents")
async def list_chat_agents():
    """获取可聊天的智能体列表（DB智能体 + 配置了 agent_prompts 的）"""
    try:
        # 从 DB 获取所有智能体
        db_agents = await storage.get_agents()
        # 从配置获取 agent_prompts
        agent_cfg = config.get("dispatcher_agent", {})
        configured_prompts = agent_cfg.get("agent_prompts", {})

        result = []
        # 先加调度员自己
        result.append({
            "id": "dispatcher",
            "name": "调度员",
            "avatar": "调",
            "color": "#3498db",
            "status": "online",
            "capabilities": "任务调度,任务管理,任务跟踪",
            "description": "任务调度智能体，帮你创建分派任务",
            "has_prompt": True,
            "group": "system",
        })

        # 再加配置了 prompt 的智能体
        AGENT_STYLES = {
            "xiao-qing": {"avatar": "青", "color": "#e67e22"},   # 橙色
            "xiao-lan":  {"avatar": "蓝", "color": "#3498db"},   # 蓝色
            "xiao-bai":  {"avatar": "白", "color": "#95a5a6"},   # 灰色
            "xiao-hei":  {"avatar": "黑", "color": "#e74c3c"},   # 红色
        }
        for agent in db_agents:
            style = AGENT_STYLES.get(agent.id, {})
            is_configured = agent.id in configured_prompts
            result.append({
                "id": agent.id,
                "name": agent.name,
                "avatar": style.get("avatar", agent.name[0] if agent.name else "?"),
                "color": style.get("color", "#95a5a6"),
                "status": agent.status,
                "capabilities": agent.capabilities,
                "description": configured_prompts[agent.id][:50] if is_configured else (agent.description or ""),
                "has_prompt": is_configured,
                "group": "member",
            })

        return {"code": 0, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
