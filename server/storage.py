"""
任务调度器 - 数据库存储模块
使用 aiosqlite 进行 SQLite 数据库操作
"""

import aiosqlite
import json
import os
from typing import Optional
from models import Task, Agent, TaskLog, CREATE_TABLES_SQL, now_str


class Storage:
    """数据库存储管理"""

    def __init__(self, db_path: str = "data/dispatcher.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def init_db(self):
        """初始化数据库，自动建表"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(CREATE_TABLES_SQL)
        # 迁移：添加智能体连接参数字段（兼容旧库）
        for col in ['connection_type', 'host', 'port', 'ssh_user', 'command_template']:
            try:
                await self._conn.execute(f"ALTER TABLE agents ADD COLUMN {col} TEXT")
            except Exception:
                pass  # 字段已存在
        await self._conn.commit()

    async def close(self):
        """关闭数据库连接"""
        if self._conn:
            await self._conn.close()

    # ==================== 任务操作 ====================

    async def create_task(self, task: Task) -> Task:
        """创建新任务"""
        if not task.id:
            import uuid
            task.id = str(uuid.uuid4())[:8]
        task.created_at = now_str()
        await self._conn.execute(
            """INSERT INTO tasks (id, title, description, priority, status, required_skills,
               assigned_to, created_at, started_at, completed_at, result, error, retry_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.title, task.description, task.priority, task.status,
             task.required_skills, task.assigned_to, task.created_at,
             task.started_at, task.completed_at, task.result, task.error, task.retry_count)
        )
        await self._conn.commit()
        return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        """根据ID获取任务"""
        cursor = await self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        if row:
            return Task(**dict(row))
        return None

    async def get_tasks(self, status: Optional[str] = None) -> list[Task]:
        """获取任务列表，可按状态筛选"""
        if status:
            cursor = await self._conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status,)
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        return [Task(**dict(r)) for r in rows]

    async def update_task(self, task_id: str, updates: dict) -> Optional[Task]:
        """更新任务字段"""
        if not updates:
            return await self.get_task(task_id)
        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        await self._conn.execute(
            f"UPDATE tasks SET {sets} WHERE id = ?", values
        )
        await self._conn.commit()
        return await self.get_task(task_id)

    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        cursor = await self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    # ==================== 智能体操作 ====================

    async def create_agent(self, agent: Agent) -> Agent:
        """注册新智能体"""
        agent.registered_at = now_str()
        agent.last_seen = now_str()
        await self._conn.execute(
            """INSERT INTO agents (id, name, capabilities, status, current_load, max_load, last_seen, registered_at,
               connection_type, host, port, ssh_user, command_template)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent.id, agent.name, agent.capabilities, agent.status,
             agent.current_load, agent.max_load, agent.last_seen, agent.registered_at,
             agent.connection_type, agent.host, agent.port, agent.ssh_user, agent.command_template)
        )
        await self._conn.commit()
        return agent

    async def get_agent(self, agent_id: str) -> Optional[Agent]:
        """根据ID获取智能体"""
        cursor = await self._conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = await cursor.fetchone()
        if row:
            data = dict(row)
            if data.get("connection_type") is None:
                data["connection_type"] = "local"
            return Agent(**data)
        return None

    async def get_agents(self, status: Optional[str] = None) -> list[Agent]:
        """获取智能体列表，可按状态筛选"""
        if status:
            cursor = await self._conn.execute(
                "SELECT * FROM agents WHERE status = ? ORDER BY registered_at DESC", (status,)
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM agents ORDER BY registered_at DESC"
            )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            data = dict(r)
            if data.get("connection_type") is None:
                data["connection_type"] = "local"
            result.append(Agent(**data))
        return result

    async def update_agent(self, agent_id: str, updates: dict) -> Optional[Agent]:
        """更新智能体字段"""
        if not updates:
            return await self.get_agent(agent_id)
        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [agent_id]
        await self._conn.execute(
            f"UPDATE agents SET {sets} WHERE id = ?", values
        )
        await self._conn.commit()
        return await self.get_agent(agent_id)

    async def delete_agent(self, agent_id: str) -> bool:
        """删除智能体"""
        cursor = await self._conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    # ==================== 日志操作 ====================

    async def add_log(self, log: TaskLog) -> TaskLog:
        """添加任务日志"""
        log.timestamp = now_str()
        cursor = await self._conn.execute(
            """INSERT INTO task_logs (task_id, agent_id, action, details, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (log.task_id, log.agent_id, log.action, log.details, log.timestamp)
        )
        await self._conn.commit()
        log.id = cursor.lastrowid
        return log

    async def get_logs(self, task_id: Optional[str] = None, limit: int = 100) -> list[TaskLog]:
        """获取日志列表，可按任务ID筛选"""
        if task_id:
            cursor = await self._conn.execute(
                "SELECT * FROM task_logs WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
                (task_id, limit)
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM task_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
        return [TaskLog(**dict(r)) for r in rows]

    # ==================== 统计 ====================

    async def get_stats(self) -> dict:
        """获取系统统计信息"""
        cursor = await self._conn.execute("SELECT COUNT(*) as c FROM tasks")
        total_tasks = (await cursor.fetchone())[0]

        cursor = await self._conn.execute("SELECT COUNT(*) as c FROM tasks WHERE status = 'queued'")
        queued = (await cursor.fetchone())[0]

        cursor = await self._conn.execute("SELECT COUNT(*) as c FROM tasks WHERE status = 'running'")
        running = (await cursor.fetchone())[0]

        cursor = await self._conn.execute("SELECT COUNT(*) as c FROM tasks WHERE status = 'completed'")
        completed = (await cursor.fetchone())[0]

        cursor = await self._conn.execute("SELECT COUNT(*) as c FROM tasks WHERE status = 'failed'")
        failed = (await cursor.fetchone())[0]

        cursor = await self._conn.execute("SELECT COUNT(*) as c FROM agents")
        total_agents = (await cursor.fetchone())[0]

        cursor = await self._conn.execute("SELECT COUNT(*) as c FROM agents WHERE status = 'online'")
        online_agents = (await cursor.fetchone())[0]

        cursor = await self._conn.execute("SELECT COUNT(*) as c FROM task_logs")
        total_logs = (await cursor.fetchone())[0]

        return {
            "total_tasks": total_tasks,
            "queued": queued,
            "running": running,
            "completed": completed,
            "failed": failed,
            "total_agents": total_agents,
            "online_agents": online_agents,
            "total_logs": total_logs,
        }

    # ==================== 聊天消息操作 ====================

    async def save_chat_message(self, session_id: str, role: str, content: str,
                                 tool_calls: str = None, tool_call_id: str = None) -> int:
        cursor = await self._conn.execute(
            """INSERT INTO chat_messages (session_id, role, content, tool_calls, tool_call_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, role, content, tool_calls, tool_call_id, now_str())
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_chat_history(self, session_id: str, limit: int = 200) -> list[dict]:
        cursor = await self._conn.execute(
            """SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC LIMIT ?""",
            (session_id, limit)
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "tool_calls": json.loads(r["tool_calls"]) if r["tool_calls"] else None,
                "tool_call_id": r["tool_call_id"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    async def get_sessions(self) -> list[dict]:
        cursor = await self._conn.execute(
            """SELECT session_id, MAX(id) as last_id, MAX(timestamp) as last_time
               FROM chat_messages GROUP BY session_id ORDER BY last_id DESC"""
        )
        rows = await cursor.fetchall()
        return [
            {
                "session_id": r["session_id"],
                "last_time": r["last_time"],
            }
            for r in rows
        ]

    async def get_session_title(self, session_id: str) -> str:
        cursor = await self._conn.execute(
            """SELECT content FROM chat_messages
               WHERE session_id = ? AND role = 'user'
               ORDER BY id ASC LIMIT 1""",
            (session_id,)
        )
        row = await cursor.fetchone()
        if row and row["content"]:
            text = row["content"]
            return text[:30] + ("..." if len(text) > 30 else "")
        return "新对话"

    async def delete_session(self, session_id: str):
        await self._conn.execute(
            "DELETE FROM chat_messages WHERE session_id = ?", (session_id,)
        )
        await self._conn.commit()

    # ==================== 记忆系统 ====================

    async def get_memory(self, key: str = None, category: str = None, tags: str = None) -> list[dict]:
        """查询记忆，支持按key/category/tags筛选"""
        conditions = []
        params = []
        if key:
            conditions.append("key = ?")
            params.append(key)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if tags:
            for tag in tags.split(","):
                tag = tag.strip()
                if tag:
                    conditions.append("tags LIKE ?")
                    params.append(f"%{tag}%")
        where = " AND ".join(conditions) if conditions else "1=1"
        cursor = await self._conn.execute(
            f"SELECT * FROM memory WHERE {where} ORDER BY category, key", params
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def set_memory(self, key: str, value: str, category: str = "general", tags: str = ""):
        """写入或更新一条记忆"""
        from models import now_str
        ts = now_str()
        await self._conn.execute(
            """INSERT INTO memory (key, value, category, tags, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
               category=excluded.category, tags=excluded.tags, updated_at=excluded.updated_at""",
            (key, value, category, tags, ts)
        )
        await self._conn.commit()

    async def delete_memory(self, key: str = None, category: str = None):
        """删除记忆"""
        conditions = []
        params = []
        if key:
            conditions.append("key = ?")
            params.append(key)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if not conditions:
            return 0
        where = " AND ".join(conditions)
        cursor = await self._conn.execute(f"DELETE FROM memory WHERE {where}", params)
        await self._conn.commit()
        return cursor.rowcount

    async def search_memory(self, query: str) -> list[dict]:
        """全文搜索记忆（key+value+tags）"""
        cursor = await self._conn.execute(
            """SELECT * FROM memory WHERE key LIKE ? OR value LIKE ? OR tags LIKE ?
               ORDER BY category, key LIMIT 20""",
            (f"%{query}%", f"%{query}%", f"%{query}%")
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
