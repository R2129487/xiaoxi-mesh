"""小希-Mesh v2 数据模型

包含智能体、消息、任务、审计日志、权限等核心数据结构。
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return uuid.uuid4().hex


# ── 智能体相关 ──

class AgentRegister(BaseModel):
    """智能体注册请求"""
    agent_id: str
    name: str
    role: str = "agent"  # admin | agent | external | readonly
    agent_type: str = "remote"  # local=本机agent | remote=远程agent
    public_key: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    capabilities: List[str] = Field(default_factory=list)
    specialties: List[str] = Field(default_factory=list)
    platform: dict = Field(default_factory=dict)  # {"os": "linux", "runtime": "python3.12"}
    description: str = ""


class Agent(BaseModel):
    """智能体信息"""
    agent_id: str
    name: str
    role: str = "agent"
    agent_type: str = "remote"  # local=本机agent | remote=远程agent
    token_hash: str = ""
    public_key: Optional[str] = None
    online: bool = False
    last_seen: Optional[datetime] = None
    registered_at: datetime = Field(default_factory=_now)
    metadata: dict = Field(default_factory=dict)
    # v2 新增
    capabilities: List[str] = Field(default_factory=list)
    specialties: List[str] = Field(default_factory=list)
    platform: dict = Field(default_factory=dict)
    description: str = ""


# ── 消息相关 ──

class Message(BaseModel):
    """消息结构"""
    id: str = Field(default_factory=_uuid)
    from_id: str
    to_id: str  # "broadcast" 表示广播
    type: str = "text"  # text | file | command | status | task | agent_call | capability_update
    content: str
    priority: str = "normal"  # normal | high
    reply_to: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    delivered: bool = False


class StatusUpdate(BaseModel):
    """状态更新"""
    agent_id: str
    status: str  # online | offline | busy
    message: Optional[str] = None


# ── 任务相关 (v2) ──

class Task(BaseModel):
    """任务模型"""
    task_id: str = Field(default_factory=_uuid)
    description: str
    assigned_to: Optional[str] = None  # agent_id, None 表示待分配
    assigned_by: str = ""  # 发起人 agent_id
    status: str = "pending"  # pending | assigned | in_progress | completed | failed
    required_capabilities: List[str] = Field(default_factory=list)
    result: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class TaskCreateRequest(BaseModel):
    """创建任务请求"""
    description: str
    assigned_to: Optional[str] = None  # 指定智能体, None/auto 表示自动路由
    required_capabilities: List[str] = Field(default_factory=list)
    assigned_by: str = "admin"


class TaskUpdateRequest(BaseModel):
    """更新任务请求"""
    status: Optional[str] = None
    result: Optional[str] = None


# ── 审计日志 (v2) ──

class AuditLog(BaseModel):
    """审计日志模型"""
    id: int = 0
    timestamp: datetime = Field(default_factory=_now)
    agent_id: str = ""
    action: str = ""  # login | logout | message_send | task_create | task_assign | capability_update | permission_change
    target: str = ""  # 操作目标
    result: str = "success"  # success | failure | denied
    details: str = ""  # JSON 字符串，额外详情


# ── 权限相关 (v2) ──

class Permission(BaseModel):
    """权限定义"""
    resource: str  # message | file | command | task | admin
    action: str  # send | receive | execute | delegate | manage
    allowed: bool = True


class RolePermissions(BaseModel):
    """角色权限配置"""
    role: str
    permissions: List[Permission] = Field(default_factory=list)


class PermissionCheck(BaseModel):
    """权限检查请求"""
    role: str
    resource: str
    action: str


# ── 认证相关 ──

class TokenPayload(BaseModel):
    """JWT Token 载荷"""
    agent_id: str
    role: str
    exp: float  # 过期时间戳
    permissions: List[dict] = Field(default_factory=list)  # v2: 嵌入权限信息


# ── 能力发现 (v2) ──

class CapabilityInfo(BaseModel):
    """能力信息"""
    capability: str
    agents: List[str] = Field(default_factory=list)  # agent_id 列表
    agent_count: int = 0


class CapabilityUpdate(BaseModel):
    """能力更新请求"""
    capabilities: List[str] = Field(default_factory=list)
    specialties: List[str] = Field(default_factory=list)


# ── 统一响应 ──

class ApiResponse(BaseModel):
    """统一 API 响应"""
    success: bool = True
    message: str = "ok"
    data: Optional[object] = None
