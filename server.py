"""小希-Mesh v2 消息中转服务 - 主服务

WebSocket (实时通信) + HTTP API (管理/离线消息/任务/审计)
协作引擎、权限控制、审计日志、能力发现集成。
新增：agent_call_response 路由、capability/params 字段转发。

启动: uvicorn server:app --host 0.0.0.0 --port 8765
"""
from __future__ import annotations
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from auth import Auth
from models import (
    Agent, Message, ApiResponse, AgentRegister, StatusUpdate,
    Task, TaskCreateRequest, TaskUpdateRequest,
    AuditLog, CapabilityInfo, CapabilityUpdate,
)
from storage import Storage
from permissions import PermissionManager
from audit import AuditLogger
from collaboration import AgentRegistry, TaskRouter, TaskDelegator, CapabilityDiscovery

# ── 配置 ──
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("xiaoxi-mesh")

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

srv_cfg = cfg["server"]
auth_cfg = cfg["auth"]
store_cfg = cfg["storage"]
limits = cfg["limits"]

auth = Auth(secret_key=auth_cfg["secret_key"],
            token_expire_hours=auth_cfg["token_expire_hours"])
store = Storage(db_path=store_cfg["db_path"])

# v2 组件
perm_mgr = PermissionManager(cfg.get("permissions", {}).get("roles", {}))
audit_log = AuditLogger(store, rate_limit_window=60, rate_limit_max=100)
registry = AgentRegistry(store)
router = TaskRouter(registry)
delegator = TaskDelegator(store, router, audit_log)
discovery = CapabilityDiscovery(registry, store)

# ── 在线连接管理 ──
connections: dict[str, WebSocket] = {}

# 跨Agent调用：call_id -> caller_agent_id
_pending_callers: dict[str, str] = {}
# 各智能体公开能力：agent_id -> [capability_name, ...]
_agent_public_caps: dict[str, set[str]] = {}


# ── 生命周期 ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init()
    await registry.load_from_db()
    # 设置委派器的广播函数
    delegator.set_broadcast(_send_to_agent)
    log.info("小希-Mesh v2 服务启动完成")
    yield
    log.info("小希-Mesh v2 服务关闭")


app = FastAPI(title="小希-Mesh v2", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ── 辅助函数 ──
def _get_token(ws: WebSocket) -> Optional[str]:
    """从 WebSocket 请求头中提取 token"""
    auth_header = ws.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    token = ws.query_params.get("token")
    return token


async def _send_json(ws: WebSocket, data: dict) -> bool:
    """安全发送 JSON，返回是否成功"""
    try:
        await ws.send_json(data)
        return True
    except Exception:
        return False


async def _send_to_agent(agent_id: str, data: dict):
    """向指定智能体发送消息（通过 WebSocket 或存储）"""
    ws = connections.get(agent_id)
    if ws:
        await _send_json(ws, data)
    else:
        # 智能体离线，存储为离线消息
        content = json.dumps(data.get("data", data))
        msg = Message(
            from_id="system",
            to_id=agent_id,
            type=data.get("type", "text"),
            content=content,
        )
        await store.save_message(msg)


async def _try_deliver(msg: Message):
    """尝试实时投递消息，投递成功标记已读"""
    if msg.to_id == "broadcast":
        for aid, ws in list(connections.items()):
            if aid != msg.from_id:
                await _send_json(ws, {
                    "type": "message",
                    "data": msg.model_dump(mode="json"),
                })
        return

    ws = connections.get(msg.to_id)
    if ws:
        await _send_json(ws, {
            "type": "message",
            "data": msg.model_dump(mode="json"),
        })
        msg.delivered = True
        await store.mark_delivered(msg.id)


# ── HTTP API ──

@app.get("/health")
async def health():
    return {"status": "ok", "agents_online": registry.online_count, "version": "2.0"}


# ── 认证 API ──

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """管理员登录"""
    admin_cfg = cfg.get("admin", {})
    if req.username != admin_cfg.get("username", "admin"):
        await audit_log.log_login(req.username, False)
        raise HTTPException(401, "用户名或密码错误")
    stored_hash = admin_cfg.get("password_hash", "")
    if not stored_hash:
        if req.password != "admin123":
            await audit_log.log_login(req.username, False)
            raise HTTPException(401, "用户名或密码错误")
    elif not auth.verify_password(req.password, stored_hash):
        await audit_log.log_login(req.username, False)
        raise HTTPException(401, "用户名或密码错误")

    # 获取权限列表
    permissions = perm_mgr.get_permissions_for_token("admin")
    token = auth.create_token_with_permissions("admin", "admin", permissions)
    await audit_log.log_login("admin", True)
    return ApiResponse(data={
        "token": token,
        "role": "admin",
        "permissions": permissions,
        "expires_in": auth_cfg["token_expire_hours"] * 3600,
    })


# ── 智能体管理 API ──

@app.post("/api/agents/register")
async def register_agent(reg: AgentRegister, authorization: str = Header(None)):
    """注册智能体（需要 admin 或 agent token 验证）"""
    token = authorization or ""
    if token.startswith("Bearer "):
        token = token[7:]
    if not token:
        raise HTTPException(401, "缺少 token，请先用管理员账号登录获取")

    if token:
        payload = auth.verify_token(token)
        if not payload or payload.role not in ("admin", "agent"):
            raise HTTPException(403, "无权限注册")

    agent = Agent(
        agent_id=reg.agent_id,
        name=reg.name,
        role=reg.role,
        public_key=reg.public_key,
        metadata=reg.metadata,
        capabilities=reg.capabilities,
        specialties=reg.specialties,
        platform=reg.platform,
        description=reg.description,
    )
    ok = await registry.register(agent)
    if not ok:
        raise HTTPException(409, f"智能体 {reg.agent_id} 已存在")

    permissions = perm_mgr.get_permissions_for_token(reg.role)
    token_str = auth.create_token_with_permissions(reg.agent_id, reg.role, permissions)
    token_hash = auth.hash_token(token_str)
    await store.set_token_hash(reg.agent_id, token_hash)
    await registry.update_capabilities(reg.agent_id, reg.capabilities, reg.specialties)

    await audit_log.log(reg.agent_id, "agent_register", reg.agent_id)

    return ApiResponse(data={
        "agent_id": reg.agent_id,
        "token": token_str,
        "role": reg.role,
        "permissions": permissions,
    })


@app.get("/api/agents")
async def list_agents():
    """获取所有智能体列表"""
    agents = registry.get_all()
    return ApiResponse(data=[
        {
            "agent_id": a.agent_id,
            "name": a.name,
            "role": a.role,
            "online": a.online,
            "last_seen": a.last_seen.isoformat() if a.last_seen else None,
            "capabilities": a.capabilities,
            "specialties": a.specialties,
            "description": a.description,
        }
        for a in agents
    ])


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """获取单个智能体信息"""
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(404, "智能体不存在")
    return ApiResponse(data=agent.model_dump(mode="json"))


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """删除智能体"""
    ok = await registry.unregister(agent_id)
    if not ok:
        raise HTTPException(404, "智能体不存在")
    await audit_log.log("admin", "agent_delete", agent_id)
    return ApiResponse(message="已删除")


@app.post("/api/agents/{agent_id}/capabilities")
async def update_agent_capabilities(agent_id: str, cap: CapabilityUpdate):
    """更新智能体能力"""
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(404, "智能体不存在")
    await registry.update_capabilities(agent_id, cap.capabilities, cap.specialties)
    await audit_log.log_capability_update(agent_id, cap.capabilities)
    return ApiResponse(message="能力已更新")


@app.get("/api/messages/{agent_id}")
async def get_undelivered(agent_id: str):
    """获取离线消息"""
    msgs = await store.get_undelivered(agent_id)
    await store.mark_all_delivered(agent_id)
    return ApiResponse(data=[m.model_dump(mode="json") for m in msgs])


class SendMessageRequest(BaseModel):
    from_id: str
    to_id: str
    type: str = "text"
    content: str
    priority: str = "normal"


@app.post("/api/messages/send")
async def send_message_http(req: SendMessageRequest):
    """通过 HTTP 发送消息"""
    msg = Message(
        from_id=req.from_id,
        to_id=req.to_id,
        type=req.type,
        content=req.content,
        priority=req.priority,
    )
    await store.save_message(msg)
    await _try_deliver(msg)
    await audit_log.log_message(req.from_id, req.to_id, req.type)
    return ApiResponse(data={"message_id": msg.id})


@app.post("/api/agents/status")
async def update_status(status: StatusUpdate):
    """更新智能体状态"""
    online = status.status == "online"
    await store.set_online(status.agent_id, online)
    return ApiResponse()


# ── 能力发现 API ──

@app.get("/api/capabilities")
async def list_capabilities():
    """获取所有能力及其智能体分布"""
    caps = discovery.get_all_capabilities()
    return ApiResponse(data={k: v.model_dump() for k, v in caps.items()})


@app.get("/api/capabilities/{capability}")
async def get_capability_agents(capability: str):
    """获取具备某能力的智能体"""
    agents = discovery.get_agents_with_capability(capability)
    return ApiResponse(data=[
        {"agent_id": a.agent_id, "name": a.name, "online": a.online}
        for a in agents
    ])


@app.get("/api/capabilities/matrix/all")
async def get_capability_matrix():
    """获取能力矩阵"""
    matrix = discovery.get_capability_matrix()
    return ApiResponse(data=matrix)


@app.get("/api/capabilities/stats/overview")
async def get_capability_stats():
    """获取能力统计"""
    stats = discovery.get_capability_stats()
    return ApiResponse(data=stats)


@app.get("/api/capabilities/search/{query}")
async def search_capabilities(query: str):
    """搜索能力"""
    results = discovery.search_capabilities(query)
    return ApiResponse(data=[r.model_dump() for r in results])


# ── 任务 API ──

@app.post("/api/tasks")
async def create_task(req: TaskCreateRequest):
    """创建任务（自动路由）"""
    task = await delegator.create_task(
        description=req.description,
        required_capabilities=req.required_capabilities,
        assigned_to=req.assigned_to,
        assigned_by=req.assigned_by,
    )
    return ApiResponse(data=task.model_dump(mode="json"))


@app.get("/api/tasks")
async def list_tasks(status: Optional[str] = None, agent_id: Optional[str] = None):
    """获取任务列表"""
    tasks = await store.list_tasks(status=status, agent_id=agent_id)
    return ApiResponse(data=[t.model_dump(mode="json") for t in tasks])


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    task = await store.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return ApiResponse(data=task.model_dump(mode="json"))


@app.post("/api/tasks/{task_id}/update")
async def update_task(task_id: str, req: TaskUpdateRequest):
    """更新任务状态"""
    if req.status:
        await store.update_task(task_id, status=req.status)
    if req.result:
        await store.update_task(task_id, result=req.result)
    task = await store.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return ApiResponse(data=task.model_dump(mode="json"))


@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str, result: str = ""):
    """完成任务"""
    task = await delegator.complete_task(task_id, result)
    if not task:
        raise HTTPException(404, "任务不存在")
    return ApiResponse(data=task.model_dump(mode="json"))


@app.post("/api/tasks/{task_id}/reassign")
async def reassign_task(task_id: str, agent_id: str = "auto"):
    """重新分配任务"""
    task = await delegator.reassign_task(task_id, agent_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return ApiResponse(data=task.model_dump(mode="json"))


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    ok = await store.delete_task(task_id)
    if not ok:
        raise HTTPException(404, "任务不存在")
    return ApiResponse(message="已删除")


# ── 审计日志 API ──

@app.get("/api/audit")
async def get_audit_logs(limit: int = 100, agent_id: Optional[str] = None,
                         action: Optional[str] = None):
    """获取审计日志"""
    logs = await audit_log.get_logs(limit, agent_id, action)
    return ApiResponse(data=[
        {
            "id": l.id,
            "timestamp": l.timestamp.isoformat() if hasattr(l.timestamp, 'isoformat') else str(l.timestamp),
            "agent_id": l.agent_id,
            "action": l.action,
            "target": l.target,
            "result": l.result,
            "details": l.details,
        }
        for l in logs
    ])


@app.get("/api/audit/recent")
async def get_recent_activity(limit: int = 20):
    """获取最近活动"""
    activity = await audit_log.get_recent_activity(limit)
    return ApiResponse(data=activity)


@app.get("/api/audit/rate-stats")
async def get_rate_stats(agent_id: Optional[str] = None):
    """获取操作频率统计"""
    stats = audit_log.get_rate_stats(agent_id)
    return ApiResponse(data=stats)


# ── 统计 API ──

@app.get("/api/stats")
async def get_stats():
    """获取系统统计"""
    stats = await store.get_stats()
    stats["capabilities"] = len(discovery.get_all_capabilities())
    return ApiResponse(data=stats)


# ── Token 管理 API ──

@app.post("/api/tokens/create")
async def create_token(agent_id: str, role: str = "agent"):
    """为智能体生成新 token"""
    agent = await store.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "智能体不存在")
    permissions = perm_mgr.get_permissions_for_token(role)
    token_str = auth.create_token_with_permissions(agent_id, role, permissions)
    token_hash = auth.hash_token(token_str)
    await store.set_token_hash(agent_id, token_hash)
    return ApiResponse(data={"token": token_str, "role": role})


@app.post("/api/tokens/revoke/{token_id}")
async def revoke_token(token_id: str):
    """撤销 token"""
    await store.revoke_token(token_id)
    return ApiResponse(message="已撤销")


@app.get("/api/tokens")
async def list_tokens(agent_id: Optional[str] = None):
    """列出 token"""
    tokens = await store.list_tokens(agent_id)
    return ApiResponse(data=tokens)


# ── 权限 API ──

@app.get("/api/permissions")
async def get_permissions():
    """获取所有权限配置"""
    return ApiResponse(data=perm_mgr._permissions)

@app.get("/api/permissions/{role}")
async def get_role_permissions(role: str):
    """获取角色权限"""
    perms = perm_mgr.get_role_permissions(role)
    return ApiResponse(data=perms)

@app.get("/api/permissions/roles/all")
async def get_all_roles():
    """获取所有角色"""
    return ApiResponse(data=perm_mgr.get_all_roles())


# ── Web 管理界面 ──

@app.get("/web/", response_class=HTMLResponse)
async def web_index():
    """Web 管理界面入口"""
    return _get_web_html()

@app.get("/web/login", response_class=HTMLResponse)
async def web_login():
    """Web 登录页面"""
    return _get_web_html()

# ── WebSocket (实时通信) ──

@app.websocket("/ws/{agent_id}")
async def websocket_endpoint(ws: WebSocket, agent_id: str):
    """WebSocket 实时消息通道"""
    # 验证 token
    token = _get_token(ws)
    if not token:
        await ws.close(code=4001, reason="缺少 token")
        return

    payload = auth.verify_token(token)
    if not payload or payload.agent_id != agent_id:
        await ws.close(code=4001, reason="token 验证失败")
        return

    # 检查是否已注册
    agent = registry.get(agent_id)
    if not agent:
        await ws.close(code=4001, reason="智能体未注册，请先调用 /api/agents/register")
        return

    await ws.accept()
    connections[agent_id] = ws
    registry.set_online(agent_id)
    await store.set_online(agent_id, True)
    await audit_log.log_login(agent_id, True)

    # 广播上线通知（排除自己）
    await _send_broadcast({
        "type": "status",
        "data": {"agent_id": agent_id, "status": "online", "name": agent.name},
    }, exclude_id=agent_id)

    # 投递离线消息（逐条标记，失败的保留未投递）
    undelivered = await store.get_undelivered(agent_id)
    for msg in undelivered:
        ok = await _send_json(ws, {"type": "message", "data": msg.model_dump(mode="json")})
        if ok:
            await store.mark_delivered(msg.id)

    log.info(f"[{agent_id}] 已连接 (在线: {len(connections)})")

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await _send_json(ws, {"type": "error", "message": "JSON 格式错误"})
                continue

            msg_type = data.get("type", "")

            if msg_type == "ping":
                await _send_json(ws, {"type": "pong"})

            elif msg_type == "send":
                # 发送消息
                msg = Message(
                    from_id=agent_id,
                    to_id=data.get("to", "broadcast"),
                    type=data.get("data_type", "text"),
                    content=data.get("content", ""),
                    priority=data.get("priority", "normal"),
                    reply_to=data.get("reply_to"),
                )
                # 大小限制
                if len(msg.content) > limits["max_message_size"]:
                    await _send_json(ws, {"type": "error", "message": "消息超过大小限制"})
                    continue

                await store.save_message(msg)
                await _try_deliver(msg)
                await audit_log.log_message(agent_id, msg.to_id, msg.type)

                # 发送确认
                await _send_json(ws, {
                    "type": "sent",
                    "data": {"message_id": msg.id},
                })

            elif msg_type == "status":
                status = data.get("status", "online")
                online = status == "online"
                if online:
                    registry.set_online(agent_id)
                else:
                    registry.set_offline(agent_id)
                await store.set_online(agent_id, online)
                await _send_broadcast({
                    "type": "status",
                    "data": {"agent_id": agent_id, "status": status},
                })

            elif msg_type == "task":
                # 任务委派 (支持 to="auto" 自动路由)
                to_id = data.get("to", "auto")
                task_desc = data.get("description", data.get("content", ""))
                required_caps = data.get("required_capabilities", [])

                task = await delegator.create_task(
                    description=task_desc,
                    required_capabilities=required_caps,
                    assigned_to=to_id,
                    assigned_by=agent_id,
                )
                await _send_json(ws, {
                    "type": "task_created",
                    "data": task.model_dump(mode="json"),
                })

            elif msg_type == "task_update":
                # 更新任务状态
                task_id = data.get("task_id", "")
                new_status = data.get("status", "")
                result = data.get("result", "")
                if task_id:
                    if new_status:
                        await store.update_task(task_id, status=new_status)
                    if result:
                        await store.update_task(task_id, result=result)
                    await _send_json(ws, {"type": "task_updated", "data": {"task_id": task_id}})

            elif msg_type == "agent_call":
                # 智能体互相调用（支持 capability + params）
                target_id = data.get("to", "")
                capability = data.get("capability", "")
                call_id = data.get("call_id", "")
                
                if not target_id:
                    await _send_json(ws, {"type": "error", "message": "缺少目标智能体"})
                    continue
                
                # 检查目标是否已注册
                if not registry.get(target_id):
                    if call_id:
                        await _send_json(ws, {"type": "agent_call_response", "call_id": call_id, "error": f"目标智能体 {target_id} 未注册"})
                    else:
                        await _send_json(ws, {"type": "error", "message": f"目标智能体 {target_id} 未注册"})
                    continue
                
                # 权限检查：调用方是否有 invoke:call 权限
                # 从注册表获取调用方真实角色
                _caller = registry.get(agent_id)
                caller_role = _caller.role if _caller else "agent"
                if not perm_mgr.check(caller_role, "invoke", "call"):
                    if call_id:
                        await _send_json(ws, {"type": "agent_call_response", "call_id": call_id, "error": "无调用权限 (invoke:call)"})
                    else:
                        await _send_json(ws, {"type": "error", "message": "无调用权限 (invoke:call)"})
                    log.warning(f"[{agent_id}] 调用被拒绝: 无 invoke:call 权限")
                    continue
                
                # 能力可见性检查：目标能力是否公开
                if capability and target_id in _agent_public_caps:
                    public_caps = _agent_public_caps.get(target_id, set())
                    if public_caps and capability not in public_caps:
                        if call_id:
                            await _send_json(ws, {"type": "agent_call_response", "call_id": call_id, "error": f"能力 {capability} 不可被外部调用"})
                        else:
                            await _send_json(ws, {"type": "error", "message": f"能力 {capability} 不可被外部调用"})
                        log.warning(f"[{agent_id}] 调用被拒绝: {target_id}.{capability} 非公开")
                        continue
                
                # 记录调用者，用于响应路由
                if call_id:
                    _pending_callers[call_id] = agent_id
                
                call_msg = {
                    "type": "agent_call",
                    "data": {
                        "from_id": agent_id,
                        "content": data.get("content", ""),
                        "call_id": call_id,
                        "capability": capability,
                        "params": data.get("params", {}),
                    }
                }
                await _send_to_agent(target_id, call_msg)
                await _send_json(ws, {"type": "call_sent", "data": {"to": target_id}})
                log.info(f"[{agent_id}] 调用 -> {target_id}.{capability} (call_id={call_id})")

            elif msg_type == "agent_call_response":
                # 智能体调用响应 - 路由回发起调用的智能体
                call_id = data.get("call_id", "")
                if call_id and call_id in _pending_callers:
                    caller_id = _pending_callers.pop(call_id)
                    response_msg = {
                        "type": "agent_call_response",
                        "call_id": call_id,
                        "data": data.get("data"),
                        "error": data.get("error"),
                    }
                    await _send_to_agent(caller_id, response_msg)
                    log.info(f"[{agent_id}] 响应 -> {caller_id} (call_id={call_id})")
                elif call_id:
                    # 找不到调用者，广播
                    response_msg = {
                        "type": "agent_call_response",
                        "call_id": call_id,
                        "data": data.get("data"),
                        "error": data.get("error"),
                    }
                    await _send_broadcast(response_msg)


            elif msg_type == "capability_update":
                # 能力更新
                capabilities = data.get("capabilities", [])
                specialties = data.get("specialties", [])
                await registry.update_capabilities(agent_id, capabilities, specialties)
                # 记录公开能力
                public_caps = data.get("public_capabilities", [])
                _agent_public_caps[agent_id] = set(public_caps)
                await audit_log.log_capability_update(agent_id, capabilities)
                # 广播能力更新通知
                await _send_broadcast({
                    "type": "capability_update",
                    "data": {
                        "agent_id": agent_id,
                        "capabilities": capabilities,
                        "specialties": specialties,
                    }
                })

            elif msg_type == "discover":
                # 能力发现查询
                query = data.get("query", "")
                if query:
                    results = discovery.search_capabilities(query)
                    await _send_json(ws, {
                        "type": "discovery_result",
                        "data": [r.model_dump() for r in results],
                    })
                else:
                    matrix = discovery.get_capability_matrix()
                    await _send_json(ws, {
                        "type": "discovery_result",
                        "data": matrix,
                    })

    except WebSocketDisconnect:
        pass
    finally:
        connections.pop(agent_id, None)
        registry.set_offline(agent_id)
        await store.set_online(agent_id, False)
        await audit_log.log_logout(agent_id)
        await _send_broadcast({
            "type": "status",
            "data": {"agent_id": agent_id, "status": "offline"},
        })
        log.info(f"[{agent_id}] 已断开 (在线: {len(connections)})")


async def _send_broadcast(data: dict, exclude_id: str = ""):
    """向所有在线智能体广播（可排除发送者）"""
    for aid, ws in list(connections.items()):
        if aid != exclude_id:
            await _send_json(ws, data)


# ── Web 管理界面 HTML ──

def _get_web_html() -> str:
    """返回管理界面 HTML"""
    return _WEB_HTML


_WEB_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>小希-Mesh 管理后台</title>
<script src="/static/tailwind.js"></script>
<script defer src="/static/alpine.min.js"></script>
<style>
[x-cloak] { display: none !important; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
.fade-in { animation: fadeIn 0.3s ease-in; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
</style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen" x-data="app()" x-init="init()">

<!-- 登录页面 -->
<template x-if="!token">
<div class="min-h-screen flex items-center justify-center">
  <div class="bg-gray-800 rounded-2xl p-8 w-full max-w-md shadow-2xl border border-gray-700">
    <div class="text-center mb-8">
      <h1 class="text-3xl font-bold text-blue-400">🤖 小希-Mesh</h1>
      <p class="text-gray-400 mt-2">智能体协作网络管理后台</p>
      <p class="text-gray-500 text-sm mt-1">v2.0</p>
    </div>
    <form @submit.prevent="login()">
      <div class="mb-4">
        <label class="block text-sm text-gray-400 mb-1">用户名</label>
        <input x-model="loginForm.username" type="text"
          class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500 text-white"
          placeholder="admin" />
      </div>
      <div class="mb-6">
        <label class="block text-sm text-gray-400 mb-1">密码</label>
        <input x-model="loginForm.password" type="password"
          class="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500 text-white"
          placeholder="admin123" />
      </div>
      <button type="submit"
        class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg transition">
        登 录
      </button>
      <p x-show="loginError" class="text-red-400 text-sm mt-3 text-center" x-text="loginError"></p>
    </form>
  </div>
</div>
</template>

<!-- 主界面 -->
<template x-if="token">
<div class="flex min-h-screen">
  <!-- 侧边栏 -->
  <aside class="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
    <div class="p-4 border-b border-gray-700">
      <h1 class="text-xl font-bold text-blue-400">🤖 小希-Mesh</h1>
      <p class="text-xs text-gray-500 mt-1">v2.0 管理后台</p>
    </div>
    <nav class="flex-1 p-2">
      <template x-for="item in menuItems" :key="item.id">
      <button @click="currentPage = item.id; loadPage()"
        :class="currentPage === item.id ? 'bg-blue-600/20 text-blue-400' : 'text-gray-400 hover:bg-gray-700 hover:text-gray-200'"
        class="w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2 mb-1 transition">
        <span x-text="item.icon"></span>
        <span x-text="item.label"></span>
      </button>
      </template>
    </nav>
    <div class="p-4 border-t border-gray-700">
      <button @click="logout()" class="text-sm text-gray-500 hover:text-red-400 transition">退出登录</button>
    </div>
  </aside>

  <!-- 主内容区 -->
  <main class="flex-1 p-6 overflow-auto">
    <!-- Dashboard -->
    <div x-show="currentPage === 'dashboard'" class="fade-in">
      <h2 class="text-2xl font-bold mb-6">📊 Dashboard</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <div class="text-gray-400 text-sm">在线智能体</div>
          <div class="text-3xl font-bold text-green-400 mt-1" x-text="stats.online_count || 0"></div>
        </div>
        <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <div class="text-gray-400 text-sm">总智能体</div>
          <div class="text-3xl font-bold text-blue-400 mt-1" x-text="stats.agent_count || 0"></div>
        </div>
        <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <div class="text-gray-400 text-sm">总消息数</div>
          <div class="text-3xl font-bold text-purple-400 mt-1" x-text="stats.message_count || 0"></div>
        </div>
        <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <div class="text-gray-400 text-sm">待处理任务</div>
          <div class="text-3xl font-bold text-yellow-400 mt-1" x-text="stats.pending_tasks || 0"></div>
        </div>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <h3 class="text-lg font-semibold mb-4 text-gray-300">在线智能体</h3>
          <template x-for="a in agents.filter(a => a.online)" :key="a.agent_id">
          <div class="flex items-center justify-between py-2 border-b border-gray-700 last:border-0">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 bg-green-400 rounded-full"></span>
              <span class="text-sm" x-text="a.name"></span>
            </div>
            <span class="text-xs text-gray-500" x-text="a.agent_id"></span>
          </div>
          </template>
          <p x-show="agents.filter(a => a.online).length === 0" class="text-gray-500 text-sm">暂无在线智能体</p>
        </div>
        <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <h3 class="text-lg font-semibold mb-4 text-gray-300">最近活动</h3>
          <template x-for="a in recentActivity" :key="a.timestamp + a.action">
          <div class="py-2 border-b border-gray-700 last:border-0">
            <div class="flex items-center justify-between">
              <span class="text-sm" x-text="a.action"></span>
              <span class="text-xs px-2 py-0.5 rounded-full"
                :class="a.result === 'success' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'"
                x-text="a.result"></span>
            </div>
            <div class="text-xs text-gray-500 mt-1">
              <span x-text="a.agent_id"></span> · <span x-text="formatTime(a.timestamp)"></span>
            </div>
          </div>
          </template>
          <p x-show="recentActivity.length === 0" class="text-gray-500 text-sm">暂无活动记录</p>
        </div>
      </div>
    </div>

    <!-- 智能体管理 -->
    <div x-show="currentPage === 'agents'" class="fade-in">
      <h2 class="text-2xl font-bold mb-6">🤖 智能体管理</h2>
      <div class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-750 border-b border-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-sm text-gray-400">状态</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">名称</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">ID</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">角色</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">能力</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">操作</th>
            </tr>
          </thead>
          <tbody>
            <template x-for="a in agents" :key="a.agent_id">
            <tr class="border-b border-gray-700 hover:bg-gray-750">
              <td class="px-4 py-3">
                <span class="w-2 h-2 rounded-full inline-block"
                  :class="a.online ? 'bg-green-400' : 'bg-gray-500'"></span>
              </td>
              <td class="px-4 py-3 text-sm font-medium" x-text="a.name"></td>
              <td class="px-4 py-3 text-xs text-gray-400" x-text="a.agent_id"></td>
              <td class="px-4 py-3">
                <span class="text-xs px-2 py-0.5 rounded-full"
                  :class="a.role === 'admin' ? 'bg-red-900 text-red-300' : 'bg-blue-900 text-blue-300'"
                  x-text="a.role"></span>
              </td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap gap-1">
                  <template x-for="cap in (a.capabilities || []).slice(0, 3)" :key="cap">
                  <span class="text-xs bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded" x-text="cap"></span>
                  </template>
                  <span x-show="(a.capabilities || []).length > 3" class="text-xs text-gray-500"
                    x-text="'+' + ((a.capabilities || []).length - 3)"></span>
                </div>
              </td>
              <td class="px-4 py-3">
                <button @click="deleteAgent(a.agent_id)"
                  class="text-xs text-red-400 hover:text-red-300">删除</button>
              </td>
            </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 能力发现 -->
    <div x-show="currentPage === 'capabilities'" class="fade-in">
      <h2 class="text-2xl font-bold mb-6">🔍 能力发现</h2>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <h3 class="text-lg font-semibold mb-4 text-gray-300">能力分布</h3>
          <template x-for="(info, cap) in capabilities" :key="cap">
          <div class="flex items-center justify-between py-2 border-b border-gray-700 last:border-0">
            <span class="text-sm" x-text="cap"></span>
            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-400" x-text="info.agent_count + ' 个智能体'"></span>
              <div class="w-20 bg-gray-700 rounded-full h-1.5">
                <div class="bg-blue-500 h-1.5 rounded-full"
                  :style="'width:' + Math.min(info.agent_count * 20, 100) + '%'"></div>
              </div>
            </div>
          </div>
          </template>
          <p x-show="Object.keys(capabilities).length === 0" class="text-gray-500 text-sm">暂无能力数据</p>
        </div>
        <div class="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <h3 class="text-lg font-semibold mb-4 text-gray-300">能力矩阵</h3>
          <div class="overflow-auto max-h-96">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-gray-400 text-left">
                  <th class="pb-2">智能体</th>
                  <th class="pb-2">能力</th>
                  <th class="pb-2">状态</th>
                </tr>
              </thead>
              <tbody>
                <template x-for="m in matrix" :key="m.agent_id">
                <tr class="border-t border-gray-700">
                  <td class="py-2" x-text="m.name"></td>
                  <td class="py-2">
                    <div class="flex flex-wrap gap-1">
                      <template x-for="cap in m.capabilities" :key="cap">
                      <span class="text-xs bg-blue-900 text-blue-300 px-1 py-0.5 rounded" x-text="cap"></span>
                      </template>
                    </div>
                  </td>
                  <td class="py-2">
                    <span class="w-2 h-2 rounded-full inline-block"
                      :class="m.online ? 'bg-green-400' : 'bg-gray-500'"></span>
                  </td>
                </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- 任务管理 -->
    <div x-show="currentPage === 'tasks'" class="fade-in">
      <h2 class="text-2xl font-bold mb-6">📋 任务管理</h2>
      <div class="mb-4 flex gap-2">
        <select x-model="taskFilter" @change="loadTasks()"
          class="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none">
          <option value="">全部状态</option>
          <option value="pending">待分配</option>
          <option value="assigned">已分配</option>
          <option value="in_progress">进行中</option>
          <option value="completed">已完成</option>
          <option value="failed">已失败</option>
        </select>
      </div>
      <div class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-750 border-b border-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-sm text-gray-400">状态</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">描述</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">分配给</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">发起人</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">创建时间</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">操作</th>
            </tr>
          </thead>
          <tbody>
            <template x-for="t in tasks" :key="t.task_id">
            <tr class="border-b border-gray-700 hover:bg-gray-750">
              <td class="px-4 py-3">
                <span class="text-xs px-2 py-0.5 rounded-full"
                  :class="{
                    'bg-yellow-900 text-yellow-300': t.status === 'pending',
                    'bg-blue-900 text-blue-300': t.status === 'assigned',
                    'bg-purple-900 text-purple-300': t.status === 'in_progress',
                    'bg-green-900 text-green-300': t.status === 'completed',
                    'bg-red-900 text-red-300': t.status === 'failed',
                  }"
                  x-text="t.status"></span>
              </td>
              <td class="px-4 py-3 text-sm max-w-xs truncate" x-text="t.description"></td>
              <td class="px-4 py-3 text-sm text-gray-400" x-text="t.assigned_to || '-'"></td>
              <td class="px-4 py-3 text-sm text-gray-400" x-text="t.assigned_by"></td>
              <td class="px-4 py-3 text-xs text-gray-500" x-text="formatTime(t.created_at)"></td>
              <td class="px-4 py-3">
                <button @click="deleteTask(t.task_id)"
                  class="text-xs text-red-400 hover:text-red-300">删除</button>
              </td>
            </tr>
            </template>
          </tbody>
        </table>
        <p x-show="tasks.length === 0" class="text-gray-500 text-sm p-4 text-center">暂无任务</p>
      </div>
    </div>

    <!-- Token 管理 -->
    <div x-show="currentPage === 'tokens'" class="fade-in">
      <h2 class="text-2xl font-bold mb-6">🔑 Token 管理</h2>
      <div class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-750 border-b border-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-sm text-gray-400">Token ID</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">智能体</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">角色</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">创建时间</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">状态</th>
            </tr>
          </thead>
          <tbody>
            <template x-for="t in tokens" :key="t.token_id">
            <tr class="border-b border-gray-700 hover:bg-gray-750">
              <td class="px-4 py-3 text-xs font-mono text-gray-400" x-text="t.token_id?.substring(0, 16) + '...'"></td>
              <td class="px-4 py-3 text-sm" x-text="t.agent_id"></td>
              <td class="px-4 py-3 text-sm text-gray-400" x-text="t.role"></td>
              <td class="px-4 py-3 text-xs text-gray-500" x-text="formatTime(t.created_at)"></td>
              <td class="px-4 py-3">
                <span class="text-xs px-2 py-0.5 rounded-full"
                  :class="t.revoked ? 'bg-red-900 text-red-300' : 'bg-green-900 text-green-300'"
                  x-text="t.revoked ? '已撤销' : '有效'"></span>
              </td>
            </tr>
            </template>
          </tbody>
        </table>
        <p x-show="tokens.length === 0" class="text-gray-500 text-sm p-4 text-center">暂无 Token</p>
      </div>
    </div>

    <!-- 审计日志 -->
    <div x-show="currentPage === 'audit'" class="fade-in">
      <h2 class="text-2xl font-bold mb-6">📝 审计日志</h2>
      <div class="mb-4 flex gap-2">
        <select x-model="auditFilter" @change="loadAudit()"
          class="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none">
          <option value="">全部操作</option>
          <option value="login">登录</option>
          <option value="logout">登出</option>
          <option value="message_send">消息发送</option>
          <option value="task_create">任务创建</option>
          <option value="task_assign">任务分配</option>
          <option value="capability_update">能力更新</option>
        </select>
      </div>
      <div class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-750 border-b border-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-sm text-gray-400">时间</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">操作</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">智能体</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">目标</th>
              <th class="px-4 py-3 text-left text-sm text-gray-400">结果</th>
            </tr>
          </thead>
          <tbody>
            <template x-for="l in auditLogs" :key="l.id || l.timestamp">
            <tr class="border-b border-gray-700 hover:bg-gray-750">
              <td class="px-4 py-3 text-xs text-gray-500" x-text="formatTime(l.timestamp)"></td>
              <td class="px-4 py-3 text-sm" x-text="l.action"></td>
              <td class="px-4 py-3 text-sm text-gray-400" x-text="l.agent_id || '-'"></td>
              <td class="px-4 py-3 text-sm text-gray-400" x-text="l.target || '-'"></td>
              <td class="px-4 py-3">
                <span class="text-xs px-2 py-0.5 rounded-full"
                  :class="l.result === 'success' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'"
                  x-text="l.result"></span>
              </td>
            </tr>
            </template>
          </tbody>
        </table>
        <p x-show="auditLogs.length === 0" class="text-gray-500 text-sm p-4 text-center">暂无日志</p>
      </div>
    </div>
  </main>
</div>
</template>

<script>
function app() {
  return {
    token: localStorage.getItem('xiaoxi_token') || '',
    loginForm: { username: '', password: 'admin123' },
    loginError: '',
    currentPage: 'dashboard',
    stats: {},
    agents: [],
    capabilities: {},
    matrix: [],
    tasks: [],
    tokens: [],
    auditLogs: [],
    recentActivity: [],
    taskFilter: '',
    auditFilter: '',
    menuItems: [
      { id: 'dashboard', label: 'Dashboard', icon: '📊' },
      { id: 'agents', label: '智能体管理', icon: '🤖' },
      { id: 'capabilities', label: '能力发现', icon: '🔍' },
      { id: 'tasks', label: '任务管理', icon: '📋' },
      { id: 'tokens', label: 'Token 管理', icon: '🔑' },
      { id: 'audit', label: '审计日志', icon: '📝' },
    ],

    async init() {
      if (this.token) {
        await this.loadPage();
      }
    },

    async api(method, path, body = null) {
      const opts = {
        method,
        headers: { 'Authorization': 'Bearer ' + this.token, 'Content-Type': 'application/json' },
      };
      if (body) opts.body = JSON.stringify(body);
      const res = await fetch(path, opts);
      if (res.status === 401) { this.token = ''; localStorage.removeItem('xiaoxi_token'); return null; }
      return await res.json();
    },

    async login() {
      this.loginError = '';
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.loginForm),
        });
        const data = await res.json();
        if (data.success && data.data?.token) {
          this.token = data.data.token;
          localStorage.setItem('xiaoxi_token', this.token);
          await this.loadPage();
        } else {
          this.loginError = data.message || '登录失败';
        }
      } catch (e) {
        this.loginError = '网络错误';
      }
    },

    logout() {
      this.token = '';
      localStorage.removeItem('xiaoxi_token');
    },

    async loadPage() {
      switch (this.currentPage) {
        case 'dashboard': await this.loadDashboard(); break;
        case 'agents': await this.loadAgents(); break;
        case 'capabilities': await this.loadCapabilities(); break;
        case 'tasks': await this.loadTasks(); break;
        case 'tokens': await this.loadTokens(); break;
        case 'audit': await this.loadAudit(); break;
      }
    },

    async loadDashboard() {
      const [statsRes, agentsRes, auditRes] = await Promise.all([
        this.api('GET', '/api/stats'),
        this.api('GET', '/api/agents'),
        this.api('GET', '/api/audit/recent?limit=10'),
      ]);
      if (statsRes?.data) this.stats = statsRes.data;
      if (agentsRes?.data) this.agents = agentsRes.data;
      if (auditRes?.data) this.recentActivity = auditRes.data;
    },

    async loadAgents() {
      const res = await this.api('GET', '/api/agents');
      if (res?.data) this.agents = res.data;
    },

    async loadCapabilities() {
      const [capsRes, matrixRes] = await Promise.all([
        this.api('GET', '/api/capabilities'),
        this.api('GET', '/api/capabilities/matrix/all'),
      ]);
      if (capsRes?.data) this.capabilities = capsRes.data;
      if (matrixRes?.data) this.matrix = matrixRes.data;
    },

    async loadTasks() {
      const url = '/api/tasks' + (this.taskFilter ? '?status=' + this.taskFilter : '');
      const res = await this.api('GET', url);
      if (res?.data) this.tasks = res.data;
    },

    async loadTokens() {
      const res = await this.api('GET', '/api/tokens');
      if (res?.data) this.tokens = res.data;
    },

    async loadAudit() {
      const url = '/api/audit?limit=100' + (this.auditFilter ? '&action=' + this.auditFilter : '');
      const res = await this.api('GET', url);
      if (res?.data) this.auditLogs = res.data;
    },

    async deleteAgent(id) {
      if (!confirm('确认删除智能体 ' + id + '？')) return;
      await this.api('DELETE', '/api/agents/' + id);
      await this.loadAgents();
    },

    async deleteTask(id) {
      if (!confirm('确认删除任务？')) return;
      await this.api('DELETE', '/api/tasks/' + id);
      await this.loadTasks();
    },

    formatTime(ts) {
      if (!ts) return '-';
      try {
        const d = new Date(ts);
        return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
      } catch { return ts; }
    },
  };
}
</script>
</body>
</html>'''


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=srv_cfg["host"], port=srv_cfg["ws_port"])
