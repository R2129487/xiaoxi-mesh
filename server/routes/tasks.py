"""
任务调度器 - 任务相关 API 路由
"""

from fastapi import APIRouter, HTTPException
from models import Task, TaskLog, now_str
from storage import Storage
from dispatcher_core import DispatcherCore

# 全局引用，在 dispatcher.py 中注入
storage: Storage = None  # type: ignore
dispatcher_core: DispatcherCore = None  # type: ignore

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("")
async def create_task(task: Task):
    """创建新任务并进行自动分派"""
    try:
        task.status = "queued"
        created = await storage.create_task(task)

        # 记录日志
        await storage.add_log(TaskLog(
            task_id=created.id,
            action="created",
            details=f"任务创建：{created.title}（优先级：{created.priority}）"
        ))

        # 自动分派
        created = await dispatcher_core.auto_dispatch(created)

        return {"code": 0, "message": "任务创建成功", "data": created.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_tasks(status: str = None):
    """获取任务列表，可按状态筛选"""
    try:
        tasks = await storage.get_tasks(status=status)
        return {"code": 0, "data": [t.model_dump() for t in tasks]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 注意：特定路径路由（/logs, /progress）必须在 /{task_id} 之前注册
@router.get("/{task_id}/logs")
async def get_task_logs(task_id: str):
    """获取任务日志"""
    try:
        task = await storage.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        logs = await storage.get_logs(task_id=task_id)
        return {"code": 0, "data": [l.model_dump() for l in logs]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/progress")
async def track_task_progress(task_id: str):
    """跟踪任务进度"""
    try:
        result = await dispatcher_core.track_progress(task_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return {"code": 0, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    try:
        task = await storage.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"code": 0, "data": task.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{task_id}")
async def update_task(task_id: str, updates: dict):
    """更新任务状态"""
    try:
        task = await storage.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 不允许更新的字段
        allowed_fields = {"status", "title", "description", "priority", "result", "error"}
        clean_updates = {k: v for k, v in updates.items() if k in allowed_fields}

        if "status" in clean_updates:
            new_status = clean_updates["status"]
            if new_status == "running" and task.status == "queued":
                clean_updates["started_at"] = now_str()
            elif new_status == "completed":
                clean_updates["completed_at"] = now_str()
            elif new_status == "failed":
                clean_updates["completed_at"] = now_str()

        updated = await storage.update_task(task_id, clean_updates)

        # 记录日志
        await storage.add_log(TaskLog(
            task_id=task_id,
            action=f"status_update",
            details=f"状态更新：{task.status} → {clean_updates.get('status', task.status)}"
        ))

        return {"code": 0, "message": "更新成功", "data": updated.model_dump() if updated else None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """取消任务"""
    try:
        task = await storage.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        await storage.update_task(task_id, {"status": "cancelled", "completed_at": now_str()})

        # 释放智能体负载
        if task.assigned_to:
            agent = await storage.get_agent(task.assigned_to)
            if agent:
                agent.current_load = max(0, agent.current_load - 1)
                await storage.update_agent(agent.id, {
                    "current_load": agent.current_load,
                    "status": "online" if agent.current_load < agent.max_load else "busy",
                })

        await storage.add_log(TaskLog(
            task_id=task_id,
            action="cancelled",
            details="任务被取消"
        ))

        return {"code": 0, "message": "任务已取消"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
