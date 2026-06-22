"""任务路由器

根据任务描述和所需能力，自动匹配最佳智能体。
评分机制：能力匹配50分 + 关键词匹配30分 + 专长匹配10分 + 在线时长奖励5分
"""
from __future__ import annotations
import logging
import re
from typing import Optional

from models import Agent

log = logging.getLogger("xiaoxi-mesh.router")


class TaskRouter:
    """任务路由器

    根据任务描述和所需能力列表，自动匹配最佳智能体。
    """

    # 评分权重
    CAPABILITY_WEIGHT = 50   # 能力匹配
    KEYWORD_WEIGHT = 30      # 关键词匹配
    SPECIALTY_WEIGHT = 10    # 专长匹配
    ONLINE_BONUS = 5         # 在线时长奖励

    def __init__(self, registry):
        self._registry = registry

    def route(self, required_capabilities: list[str] = None,
              task_description: str = "") -> Optional[Agent]:
        """根据需求匹配最佳智能体

        Args:
            required_capabilities: 需要的能力列表
            task_description: 任务描述文本

        Returns:
            最佳匹配的智能体，如果没有合适的目标则返回 None
        """
        online_agents = self._registry.get_online()
        if not online_agents:
            log.warning("没有在线智能体可用")
            return None

        scored = []
        for agent in online_agents:
            score = self._score_agent(agent, required_capabilities or [], task_description)
            if score > 0:
                scored.append((agent, score))

        if not scored:
            log.warning("没有匹配的智能体")
            return None

        # 按分数降序排列
        scored.sort(key=lambda x: x[1], reverse=True)
        best_agent, best_score = scored[0]
        log.info(f"路由结果: {best_agent.agent_id} (分数: {best_score})")
        return best_agent

    def route_all(self, required_capabilities: list[str] = None,
                  task_description: str = "") -> list[tuple[Agent, float]]:
        """路由所有匹配的智能体（按分数排序）

        Returns:
            [(agent, score), ...] 列表
        """
        online_agents = self._registry.get_online()
        scored = []
        for agent in online_agents:
            score = self._score_agent(agent, required_capabilities or [], task_description)
            if score > 0:
                scored.append((agent, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _score_agent(self, agent: Agent, required_capabilities: list[str],
                     task_description: str) -> float:
        """计算智能体匹配分数

        分数构成：
        - 能力匹配 (50分): 每匹配一个所需能力得满分/总需求数
        - 关键词匹配 (30分): 从任务描述中提取关键词，匹配智能体描述和能力
        - 专长匹配 (10分): 匹配智能体专长
        - 在线时长奖励 (5分): 在线越久分数越高
        """
        score = 0.0

        # 1. 能力匹配 (50分)
        if required_capabilities:
            matched = sum(1 for c in required_capabilities if c in agent.capabilities)
            score += (matched / len(required_capabilities)) * self.CAPABILITY_WEIGHT
        else:
            # 无能力要求，给基础分
            score += 25.0

        # 2. 关键词匹配 (30分)
        if task_description:
            keywords = self._extract_keywords(task_description)
            if keywords:
                # 在智能体描述和能力中搜索关键词
                searchable = " ".join([
                    agent.description,
                    " ".join(agent.capabilities),
                    " ".join(agent.specialties),
                    agent.name,
                ]).lower()
                matched = sum(1 for kw in keywords if kw in searchable)
                score += (matched / len(keywords)) * self.KEYWORD_WEIGHT
        else:
            score += 15.0  # 无描述，给半分

        # 3. 专长匹配 (10分)
        if required_capabilities and agent.specialties:
            matched = sum(1 for c in required_capabilities if c in agent.specialties)
            score += (matched / len(required_capabilities)) * self.SPECIALTY_WEIGHT

        # 4. 在线时长奖励 (5分)
        duration = self._registry.get_online_duration(agent.agent_id)
        # 在线超过1小时得满分，按比例递减
        score += min(duration / 3600.0, 1.0) * self.ONLINE_BONUS

        return round(score, 2)

    def _extract_keywords(self, text: str) -> list[str]:
        """从文本中提取关键词

        简单实现：分割文本并过滤停用词和短词
        """
        stop_words = {
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
            "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
            "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
            "它", "们", "那", "些", "什么", "怎么", "如何", "可以", "请",
            "把", "被", "让", "给", "从", "对", "为", "与", "及", "或",
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "and",
            "but", "or", "not", "no", "if", "then", "else", "when",
            "this", "that", "these", "those", "it", "its", "my", "your",
            "his", "her", "our", "their", "me", "him", "us", "them",
        }
        # 提取中文词和英文词
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text)
        return [w.lower() for w in words if len(w) > 1 and w.lower() not in stop_words]
