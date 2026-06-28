"""调度员 - 记忆系统 API 路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/memory", tags=["memory"])

# 全局引用，在 dispatcher.py 中注入
storage: object = None  # type: ignore


@router.get("")
async def get_memory(key: str = None, category: str = None, search: str = None):
    """查询记忆"""
    try:
        if search:
            results = await storage.search_memory(search)
        else:
            results = await storage.get_memory(key=key, category=category)
        return {"code": 0, "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def set_memory(body: dict):
    """写入记忆"""
    try:
        key = body.get("key", "").strip()
        if not key:
            return {"code": 1, "message": "key 不能为空"}
        await storage.set_memory(
            key=key,
            value=body.get("value", ""),
            category=body.get("category", "general"),
            tags=body.get("tags", ""),
        )
        return {"code": 0, "message": "记忆已保存"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("")
async def delete_memory(key: str = None, category: str = None):
    """删除记忆"""
    try:
        count = await storage.delete_memory(key=key, category=category)
        return {"code": 0, "message": f"已删除 {count} 条记忆"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
