"""
任务调度器 - 数据模型模块
定义 Task、Agent、TaskLog 的数据模型
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional


class Task(BaseModel):
    """任务数据模型"""
    id: str = Field(default="", description="任务唯一ID")
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务详细描述")
    priority: str = Field(default="medium", description="优先级: low/medium/high/critical")
    status: str = Field(default="queued", description="状态: queued/analyzing/dispatched/running/completed/failed/cancelled")
    required_skills: str = Field(default="", description="所需技能(逗号分隔)")
    assigned_to: Optional[str] = Field(default=None, description="分配的智能体ID")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    started_at: Optional[str] = Field(default=None, description="开始执行时间")
    completed_at: Optional[str] = Field(default=None, description="完成时间")
    result: Optional[str] = Field(default=None, description="执行结果")
    error: Optional[str] = Field(default=None, description="错误信息")
    retry_count: int = Field(default=0, description="已重试次数")


class Agent(BaseModel):
    """智能体数据模型"""
    id: str = Field(default="", description="智能体唯一ID")
    name: str = Field(default="", description="智能体名称")
    capabilities: str = Field(default="", description="能力列表(逗号分隔)")
    status: str = Field(default="offline", description="状态: online/offline/busy")
    current_load: int = Field(default=0, description="当前负载(任务数)")
    max_load: int = Field(default=10, description="最大负载")
    last_seen: Optional[str] = Field(default=None, description="最后在线时间")
    registered_at: Optional[str] = Field(default=None, description="注册时间")
    # 连接参数
    connection_type: str = Field(default="local", description="连接方式: local/ssh/mesh/http")
    host: Optional[str] = Field(default=None, description="IP地址或主机名")
    port: Optional[int] = Field(default=None, description="SSH端口或API端口")
    ssh_user: Optional[str] = Field(default=None, description="SSH用户名")
    command_template: Optional[str] = Field(default=None, description="命令模板，如 hermes -z '{task}' --yolo")


class TaskLog(BaseModel):
    """任务日志数据模型"""
    id: Optional[int] = Field(default=None, description="日志ID")
    task_id: str = Field(default="", description="关联任务ID")
    agent_id: Optional[str] = Field(default=None, description="关联智能体ID")
    action: str = Field(default="", description="操作类型")
    details: Optional[str] = Field(default=None, description="详情描述")
    timestamp: Optional[str] = Field(default=None, description="日志时间")


# SQL 建表语句
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'queued',
    required_skills TEXT DEFAULT '',
    assigned_to TEXT,
    created_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    result TEXT,
    error TEXT,
    retry_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    tags TEXT DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    capabilities TEXT DEFAULT '',
    status TEXT DEFAULT 'offline',
    current_load INTEGER DEFAULT 0,
    max_load INTEGER DEFAULT 10,
    last_seen TEXT,
    registered_at TEXT,
    connection_type TEXT DEFAULT 'local',
    host TEXT,
    port INTEGER,
    ssh_user TEXT,
    command_template TEXT
);

CREATE TABLE IF NOT EXISTS task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    agent_id TEXT,
    action TEXT NOT NULL DEFAULT '',
    details TEXT,
    timestamp TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT DEFAULT '',
    tool_calls TEXT,
    tool_call_id TEXT,
    timestamp TEXT
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);
"""


def now_str() -> str:
    """返回当前UTC时间字符串"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
