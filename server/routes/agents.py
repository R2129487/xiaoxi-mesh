"""
任务调度器 - 智能体相关 API 路由
"""

from fastapi import APIRouter, HTTPException
from models import Agent, now_str
from storage import Storage

# 全局引用，在 dispatcher.py 中注入
storage: Storage = None  # type: ignore

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
async def list_agents(status: str = None):
    """获取智能体列表，可按状态筛选"""
    try:
        agents = await storage.get_agents(status=status)
        return {"code": 0, "data": [a.model_dump() for a in agents]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def register_agent(agent: Agent):
    """注册新智能体"""
    try:
        # 检查是否已存在
        existing = await storage.get_agent(agent.id)
        if existing:
            raise HTTPException(status_code=400, detail=f"智能体 {agent.id} 已存在")

        agent.status = "online"
        agent.last_seen = now_str()
        created = await storage.create_agent(agent)

        return {"code": 0, "message": "注册成功", "data": created.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """获取智能体详情"""
    try:
        agent = await storage.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"code": 0, "data": agent.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{agent_id}")
async def update_agent(agent_id: str, updates: dict):
    """更新智能体状态"""
    try:
        agent = await storage.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")

        allowed_fields = {"status", "name", "capabilities", "current_load", "max_load",
                         "connection_type", "host", "port", "ssh_user", "command_template"}
        clean_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        clean_updates["last_seen"] = now_str()

        updated = await storage.update_agent(agent_id, clean_updates)
        return {"code": 0, "message": "更新成功", "data": updated.model_dump() if updated else None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    """删除智能体"""
    try:
        agent = await storage.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")

        await storage.delete_agent(agent_id)
        return {"code": 0, "message": f"智能体 {agent_id} 已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
