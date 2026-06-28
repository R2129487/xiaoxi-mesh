"""调度员 - 配置管理 API 路由"""

from __future__ import annotations

import os
import yaml
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")

# 可公开的 LLM 配置字段（读/写）
LLM_FIELDS = [
    "provider",
    "base_url",
    "model",
    "max_tokens",
    "temperature",
    "top_p",
    "timeout",
]


def _load_yaml() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(data: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _read_api_key(api_key_path: str) -> str:
    """从文件读取 API Key"""
    expanded = os.path.expanduser(api_key_path)
    if os.path.exists(expanded):
        with open(expanded, "r") as f:
            return f.read().strip()
    return ""


def _write_api_key(api_key_path: str, key: str):
    """写入 API Key 到文件"""
    expanded = os.path.expanduser(api_key_path)
    os.makedirs(os.path.dirname(expanded), exist_ok=True)
    with open(expanded, "w") as f:
        f.write(key.strip())


@router.get("")
async def get_config():
    """获取调度员 LLM 配置"""
    try:
        cfg = _load_yaml()
        llm = cfg.get("dispatcher_agent", {}).get("llm", {})
        system_prompt = cfg.get("dispatcher_agent", {}).get("system_prompt", "")

        # 构建返回数据
        result = {}
        for field in LLM_FIELDS:
            result[field] = llm.get(field, "")

        # API Key 脱敏（只显示前后4位）
        api_key_path = llm.get("api_key_path", "")
        api_key = _read_api_key(api_key_path)
        masked_key = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else ""
        result["api_key_path"] = api_key_path
        result["api_key_masked"] = masked_key
        result["has_api_key"] = bool(api_key)

        return {"code": 0, "data": {
            "llm": result,
            "system_prompt": system_prompt,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("")
async def update_config(body: dict):
    """更新调度员 LLM 配置"""
    try:
        llm_config = body.get("llm", {})
        system_prompt = body.get("system_prompt")

        cfg = _load_yaml()

        # 确保 dispatcher_agent.llm 存在
        if "dispatcher_agent" not in cfg:
            cfg["dispatcher_agent"] = {}
        if "llm" not in cfg["dispatcher_agent"]:
            cfg["dispatcher_agent"]["llm"] = {}

        # 更新 LLM 字段（只更新允许的字段）
        for field in LLM_FIELDS:
            if field in llm_config:
                cfg["dispatcher_agent"]["llm"][field] = llm_config[field]

        # API Key 独立处理（写入文件）
        if "api_key" in llm_config and llm_config["api_key"]:
            api_key_path = cfg["dispatcher_agent"]["llm"].get("api_key_path", "")
            if api_key_path:
                _write_api_key(api_key_path, llm_config["api_key"])

        # 更新 system prompt
        if system_prompt is not None:
            cfg["dispatcher_agent"]["system_prompt"] = system_prompt

        _save_yaml(cfg)

        return {"code": 0, "message": "配置已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 智能体提示词管理 ====================


@router.get("/agent-prompts")
async def get_agent_prompts():
    """获取所有智能体的提示词"""
    try:
        cfg = _load_yaml()
        prompts = cfg.get("dispatcher_agent", {}).get("agent_prompts", {})
        return {"code": 0, "data": prompts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/agent-prompts/{agent_id}")
async def update_agent_prompt(agent_id: str, body: dict):
    """更新指定智能体的提示词"""
    try:
        prompt = body.get("prompt", "")
        cfg = _load_yaml()
        if "dispatcher_agent" not in cfg:
            cfg["dispatcher_agent"] = {}
        if "agent_prompts" not in cfg["dispatcher_agent"]:
            cfg["dispatcher_agent"]["agent_prompts"] = {}
        cfg["dispatcher_agent"]["agent_prompts"][agent_id] = prompt
        _save_yaml(cfg)
        return {"code": 0, "message": f"智能体 {agent_id} 提示词已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agent-prompts/{agent_id}")
async def delete_agent_prompt(agent_id: str):
    """删除智能体的提示词"""
    try:
        cfg = _load_yaml()
        prompts = cfg.get("dispatcher_agent", {}).get("agent_prompts", {})
        if agent_id in prompts:
            del prompts[agent_id]
            _save_yaml(cfg)
        return {"code": 0, "message": f"智能体 {agent_id} 提示词已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
