"""任务委派器

分析任务需求 → 路由匹配 → 创建任务记录 → 通知负责人。
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from models import Task

log = logging.getLogger("xiaoxi-mesh.delegator")


class TaskDelegator:
    """任务委派器

    协调任务的创建、路由、分配和通知流程。
    """

    def __init__(self, storage, router, audit_logger=None):
        self._storage = storage
        self._router = router
        self._audit = audit_logger
        self._broadcast_fn: Optional[Callable[[str, dict], Awaitable[None]]] = None

    def set_broadcast(self, fn: Callable[[str, dict], Awaitable[None]]):
        """设置广播函数，用于向智能体发送任务通知

        fn(agent_id, data) -> None
        """
        self._broadcast_fn = fn

    async def create_task(self, description: str, required_capabilities: list[str] = None,
                          assigned_to: str = None, assigned_by: str = "admin") -> Task:
        """创建任务

        如果指定了 assigned_to，则直接分配；
        否则自动路由到最佳智能体。
        """
        task = Task(
            description=description,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
            required_capabilities=required_capabilities or [],
        )

        # 自动路由
        if not assigned_to or assigned_to == "auto":
            agent = self._router.route(required_capabilities, description)
            if agent:
                task.assigned_to = agent.agent_id
                task.status = "assigned"
                log.info(f"任务自动路由: {task.task_id} -> {agent.agent_id}")
            else:
                task.status = "pending"
                log.warning(f"任务 {task.task_id} 无可用智能体，保持待分配")

        await self._storage.create_task(task)

        # 审计日志
        if self._audit:
            await self._audit.log(
                agent_id=assigned_by,
                action="task_create",
                target=task.task_id,
                details=json.dumps({
                    "description": description[:200],
                    "assigned_to": task.assigned_to,
                    "required_capabilities": required_capabilities or [],
                })
            )

        # 通知分配的智能体
        if task.assigned_to and self._broadcast_fn:
            await self._notify_agent(task)

        return task

    async def reassign_task(self, task_id: str, new_agent_id: str = None) -> Optional[Task]:
        """重新分配任务"""
        task = await self._storage.get_task(task_id)
        if not task:
            return None

        if new_agent_id == "auto" or not new_agent_id:
            agent = self._router.route(task.required_capabilities, task.description)
            if agent:
                new_agent_id = agent.agent_id
            else:
                log.warning(f"任务 {task_id} 重新路由失败，无可用智能体")
                return task

        await self._storage.update_task(task_id,
                                         assigned_to=new_agent_id,
                                         status="assigned")
        task.assigned_to = new_agent_id
        task.status = "assigned"

        if self._broadcast_fn:
            await self._notify_agent(task)

        if self._audit:
            await self._audit.log(
                action="task_assign",
                target=task_id,
                details=json.dumps({"new_agent": new_agent_id})
            )

        return task

    async def complete_task(self, task_id: str, result: str = "") -> Optional[Task]:
        """完成任务"""
        task = await self._storage.get_task(task_id)
        if not task:
            return None

        await self._storage.update_task(task_id, status="completed", result=result)
        task.status = "completed"
        task.result = result

        if self._audit:
            await self._audit.log(
                agent_id=task.assigned_to or "",
                action="task_complete",
                target=task_id,
                details=json.dumps({"result": result[:500]})
            )

        return task

    async def fail_task(self, task_id: str, reason: str = "") -> Optional[Task]:
        """标记任务失败"""
        task = await self._storage.get_task(task_id)
        if not task:
            return None

        await self._storage.update_task(task_id, status="failed", result=reason)
        task.status = "failed"
        task.result = reason

        if self._audit:
            await self._audit.log(
                agent_id=task.assigned_to or "",
                action="task_fail",
                target=task_id,
                details=json.dumps({"reason": reason[:500]})
            )

        return task

    async def start_task(self, task_id: str) -> Optional[Task]:
        """开始执行任务"""
        task = await self._storage.get_task(task_id)
        if not task:
            return None

        await self._storage.update_task(task_id, status="in_progress")
        task.status = "in_progress"

        if self._audit:
            await self._audit.log(
                agent_id=task.assigned_to or "",
                action="task_start",
                target=task_id
            )

        return task

    async def get_pending_tasks(self) -> list[Task]:
        """获取所有待分配任务"""
        return await self._storage.list_tasks(status="pending")

    async def _notify_agent(self, task: Task):
        """通知智能体有新任务"""
        if not task.assigned_to:
            return
        try:
            await self._broadcast_fn(task.assigned_to, {
                "type": "task",
                "data": {
                    "task_id": task.task_id,
                    "description": task.description,
                    "assigned_by": task.assigned_by,
                    "required_capabilities": task.required_capabilities,
                }
            })
            log.info(f"已通知智能体 {task.assigned_to} 接受任务 {task.task_id}")
        except Exception as e:
            log.error(f"通知智能体失败: {e}")
