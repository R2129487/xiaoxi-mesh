"""能力发现模块

查询具备特定能力的智能体、列出所有能力分布、能力矩阵。
"""
from __future__ import annotations
import logging
from typing import Optional

from models import Agent, CapabilityInfo

log = logging.getLogger("xiaoxi-mesh.discovery")


class CapabilityDiscovery:
    """能力发现服务

    提供智能体能力查询、能力矩阵、能力统计等功能。
    """

    def __init__(self, registry, storage):
        self._registry = registry
        self._storage = storage

    def get_agents_with_capability(self, capability: str) -> list[Agent]:
        """获取具备指定能力的所有在线智能体"""
        return self._registry.get_by_capability(capability)

    def get_all_capabilities(self) -> dict[str, CapabilityInfo]:
        """获取所有能力及其对应的智能体分布

        Returns:
            {capability_name: CapabilityInfo} 字典
        """
        cap_map: dict[str, list[str]] = {}
        for agent in self._registry.get_all():
            for cap in agent.capabilities:
                cap_map.setdefault(cap, []).append(agent.agent_id)

        result = {}
        for cap, agent_ids in cap_map.items():
            result[cap] = CapabilityInfo(
                capability=cap,
                agents=agent_ids,
                agent_count=len(agent_ids),
            )
        return result

    def get_capability_matrix(self) -> list[dict]:
        """获取能力矩阵

        返回格式：
        [
            {"agent_id": "xxx", "name": "yyy", "capabilities": [...], "specialties": [...], "online": true},
            ...
        ]
        """
        agents = self._registry.get_all()
        return [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "capabilities": a.capabilities,
                "specialties": a.specialties,
                "online": a.online,
            }
            for a in sorted(agents, key=lambda x: x.name)
        ]

    def search_capabilities(self, query: str) -> list[CapabilityInfo]:
        """搜索能力（模糊匹配）"""
        query_lower = query.lower()
        all_caps = self.get_all_capabilities()
        return [
            info for cap, info in all_caps.items()
            if query_lower in cap.lower()
        ]

    def get_agent_capabilities(self, agent_id: str) -> Optional[dict]:
        """获取指定智能体的能力详情"""
        agent = self._registry.get(agent_id)
        if not agent:
            return None
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "capabilities": agent.capabilities,
            "specialties": agent.specialties,
            "description": agent.description,
            "platform": agent.platform,
            "online": agent.online,
        }

    def get_capability_stats(self) -> dict:
        """获取能力统计概览"""
        all_caps = self.get_all_capabilities()
        agents = self._registry.get_all()
        online = self._registry.get_online()

        # 找出最热门和最冷门的能力
        sorted_caps = sorted(all_caps.values(), key=lambda x: x.agent_count, reverse=True)

        return {
            "total_capabilities": len(all_caps),
            "total_agents": len(agents),
            "online_agents": len(online),
            "most_common": sorted_caps[0].capability if sorted_caps else None,
            "least_common": sorted_caps[-1].capability if sorted_caps else None,
            "capabilities": {c.capability: c.agent_count for c in sorted_caps},
        }
