"""智能体注册表

内存缓存 + DB 持久化的智能体注册表，支持能力声明、状态更新、在线状态管理。
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from models import Agent

log = logging.getLogger("xiaoxi-mesh.registry")


class AgentRegistry:
    """智能体注册表

    维护内存缓存以提高查询性能，同时通过 Storage 层实现 DB 持久化。
    """

    def __init__(self, storage):
        self._storage = storage
        self._cache: dict[str, Agent] = {}  # agent_id -> Agent
        self._online_since: dict[str, float] = {}  # agent_id -> 连接时间戳
        self._loaded = False

    async def load_from_db(self):
        """从数据库加载所有智能体到内存缓存"""
        agents = await self._storage.list_agents()
        self._cache = {a.agent_id: a for a in agents}
        self._loaded = True
        log.info(f"注册表已加载 {len(self._cache)} 个智能体")

    async def register(self, agent: Agent) -> bool:
        """注册新智能体"""
        ok = await self._storage.register_agent(agent)
        if ok:
            self._cache[agent.agent_id] = agent
            log.info(f"智能体注册: {agent.agent_id} ({agent.name})")
        return ok

    async def unregister(self, agent_id: str) -> bool:
        """注销智能体"""
        ok = await self._storage.delete_agent(agent_id)
        if ok:
            self._cache.pop(agent_id, None)
            self._online_since.pop(agent_id, None)
            log.info(f"智能体注销: {agent_id}")
        return ok

    async def update_capabilities(self, agent_id: str, capabilities: list[str],
                                   specialties: list[str] | None = None):
        """更新智能体能力"""
        kwargs = {"capabilities": capabilities}
        if specialties is not None:
            kwargs["specialties"] = specialties
        await self._storage.update_agent(agent_id, **kwargs)
        if agent_id in self._cache:
            self._cache[agent_id].capabilities = capabilities
            if specialties is not None:
                self._cache[agent_id].specialties = specialties
        await self._storage.refresh_capability_cache()
        log.info(f"能力更新: {agent_id} -> {capabilities}")

    def set_online(self, agent_id: str):
        """标记智能体在线"""
        self._online_since[agent_id] = time.time()
        if agent_id in self._cache:
            self._cache[agent_id].online = True

    def set_offline(self, agent_id: str):
        """标记智能体离线"""
        self._online_since.pop(agent_id, None)
        if agent_id in self._cache:
            self._cache[agent_id].online = False

    def get(self, agent_id: str) -> Optional[Agent]:
        """获取智能体信息"""
        return self._cache.get(agent_id)

    def get_all(self) -> list[Agent]:
        """获取所有智能体"""
        return list(self._cache.values())

    def get_online(self) -> list[Agent]:
        """获取在线智能体"""
        return [a for a in self._cache.values() if a.online]

    def get_by_capability(self, capability: str) -> list[Agent]:
        """获取具备指定能力的在线智能体"""
        return [
            a for a in self._cache.values()
            if a.online and capability in a.capabilities
        ]

    def get_online_duration(self, agent_id: str) -> float:
        """获取智能体在线时长（秒）"""
        start = self._online_since.get(agent_id)
        if start:
            return time.time() - start
        return 0.0

    def has_agent(self, agent_id: str) -> bool:
        """检查智能体是否存在"""
        return agent_id in self._cache

    @property
    def online_count(self) -> int:
        return len(self._online_since)

    @property
    def total_count(self) -> int:
        return len(self._cache)
