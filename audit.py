"""小希-Mesh v2 审计日志模块

记录所有关键操作：登录、消息发送、任务分配、权限变更。
支持异常行为检测（简单频率限制）。
"""
from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timezone
from collections import defaultdict

from models import AuditLog

log = logging.getLogger("xiaoxi-mesh.audit")


class AuditLogger:
    """审计日志记录器

    记录所有关键操作，支持异常行为检测。
    """

    def __init__(self, storage, rate_limit_window: int = 60, rate_limit_max: int = 100):
        """初始化审计日志记录器

        Args:
            storage: 存储层实例
            rate_limit_window: 频率限制窗口（秒）
            rate_limit_max: 窗口内最大操作次数
        """
        self._storage = storage
        self._rate_limit_window = rate_limit_window
        self._rate_limit_max = rate_limit_max
        # 内存中的操作频率计数: {agent_id: {action: [(timestamp, count)]}}
        self._rate_counters: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        # 异常告警阈值
        self._alert_threshold = rate_limit_max * 2

    async def log(self, agent_id: str = "", action: str = "", target: str = "",
                  result: str = "success", details: str = ""):
        """记录审计日志

        Args:
            agent_id: 操作智能体
            action: 操作类型 (login, logout, message_send, task_create, task_assign, capability_update, permission_change)
            target: 操作目标
            result: 结果 (success, failure, denied)
            details: 额外详情 (JSON 字符串)
        """
        entry = AuditLog(
            timestamp=datetime.now(timezone.utc),
            agent_id=agent_id,
            action=action,
            target=target,
            result=result,
            details=details,
        )
        await self._storage.save_audit_log(entry)
        log.info(f"[审计] {agent_id} {action} -> {target} ({result})")

        # 异常行为检测
        self._check_rate_limit(agent_id, action)

    async def log_login(self, agent_id: str, success: bool = True):
        """记录登录事件"""
        await self.log(
            agent_id=agent_id,
            action="login",
            target=agent_id,
            result="success" if success else "failure",
        )

    async def log_logout(self, agent_id: str):
        """记录登出事件"""
        await self.log(
            agent_id=agent_id,
            action="logout",
            target=agent_id,
        )

    async def log_message(self, from_id: str, to_id: str, msg_type: str = "text"):
        """记录消息发送"""
        await self.log(
            agent_id=from_id,
            action="message_send",
            target=to_id,
            details=json.dumps({"type": msg_type})
        )

    async def log_task(self, agent_id: str, task_id: str, action: str = "task_create"):
        """记录任务操作"""
        await self.log(
            agent_id=agent_id,
            action=action,
            target=task_id,
        )

    async def log_capability_update(self, agent_id: str, capabilities: list[str]):
        """记录能力更新"""
        await self.log(
            agent_id=agent_id,
            action="capability_update",
            target=agent_id,
            details=json.dumps({"capabilities": capabilities})
        )

    async def log_permission_change(self, admin_id: str, target_role: str, details: str = ""):
        """记录权限变更"""
        await self.log(
            agent_id=admin_id,
            action="permission_change",
            target=target_role,
            details=details,
        )

    async def get_logs(self, limit: int = 100, agent_id: str = None,
                       action: str = None) -> list[AuditLog]:
        """获取审计日志"""
        return await self._storage.get_audit_logs(limit, agent_id, action)

    async def get_recent_activity(self, limit: int = 20) -> list[dict]:
        """获取最近活动（用于 Dashboard）"""
        logs = await self._storage.get_audit_logs(limit)
        return [
            {
                "timestamp": l.timestamp.isoformat() if isinstance(l.timestamp, str) else l.timestamp,
                "agent_id": l.agent_id,
                "action": l.action,
                "target": l.target,
                "result": l.result,
            }
            for l in logs
        ]

    def _check_rate_limit(self, agent_id: str, action: str):
        """检查操作频率是否异常"""
        if not agent_id:
            return

        now = time.time()
        window_start = now - self._rate_limit_window

        # 清理过期记录
        timestamps = self._rate_counters[agent_id][action]
        self._rate_counters[agent_id][action] = [
            t for t in timestamps if t > window_start
        ]

        # 添加新记录
        self._rate_counters[agent_id][action].append(now)

        # 检查是否超过阈值
        count = len(self._rate_counters[agent_id][action])
        if count > self._alert_threshold:
            log.warning(
                f"[审计告警] 智能体 {agent_id} 操作 {action} 频率异常: "
                f"{count} 次/{self._rate_limit_window}秒 (阈值: {self._alert_threshold})"
            )

    def get_rate_stats(self, agent_id: str = None) -> dict:
        """获取操作频率统计"""
        now = time.time()
        window_start = now - self._rate_limit_window
        stats = {}
        agents = [agent_id] if agent_id else list(self._rate_counters.keys())
        for aid in agents:
            agent_stats = {}
            for action, timestamps in self._rate_counters.get(aid, {}).items():
                recent = [t for t in timestamps if t > window_start]
                agent_stats[action] = len(recent)
            if agent_stats:
                stats[aid] = agent_stats
        return stats
