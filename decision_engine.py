#!/usr/bin/env python3
"""小希-Mesh 自主决策引擎

Agent收到任务后，自动分析需要什么能力，决定自己执行还是找其他Agent协作。

决策流程:
  1. 从任务描述中提取关键词，映射到所需能力
  2. 检查自己是否具备该能力
  3. 如果没有，查询其他在线Agent的能力
  4. 返回决策: SELF(自己干) / DELEGATE(委派) / UNKNOWN(无法判断)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger("xiaoxi-mesh.decision")


class DecisionType(Enum):
    """决策类型"""
    SELF = "self"           # 自己执行
    DELEGATE = "delegate"   # 委派给其他Agent
    UNKNOWN = "unknown"     # 无法判断，走默认流程


@dataclass
class Decision:
    """决策结果"""
    decision: DecisionType
    capability_needed: str = ""       # 需要的能力
    target_agent: str = ""            # 委派目标Agent ID
    reason: str = ""                  # 决策原因
    confidence: float = 0.0           # 置信度 0~1
    alternatives: list = field(default_factory=list)  # 备选Agent


# ── 关键词 → 能力 映射表 ──

# 每个关键词列表对应一个所需能力
KEYWORD_TO_CAPABILITY: list[tuple[list[str], str]] = [
    # 系统监控
    (["服务器", "系统状态", "监控", "cpu", "内存", "磁盘", "负载", "uptime", "运维", "系统"],
     "system_monitor"),
    # 代码生成
    (["代码", "脚本", "编程", "python", "java", "go", "rust", "开发", "写代码", "编写", "程序"],
     "code_generation"),
    # 文件下载
    (["下载", "download", "拉取", "获取文件", "wget", "curl"],
     "download_management"),
    # 网络搜索
    (["搜索", "查找", "搜索一下", "查一下", "search", "query", "google", "百度"],
     "web_search"),
    # 数据分析
    (["分析", "数据", "统计", "图表", "报表", "analytics", "数据处理"],
     "data_analysis"),
    # 桌面自动化
    (["截图", "桌面", "屏幕", "剪贴板", "clipboard", "screenshot", "GUI", "鼠标", "键盘"],
     "desktop_automation"),
    # 微信操作
    (["微信", "wechat", "消息", "朋友圈", "群聊"],
     "wechat_operations"),
    # 翻译
    (["翻译", "translate", "英文", "中文翻译", "日语"],
     "translation"),
    # SSH操作
    (["ssh", "远程", "连接服务器", "terminal", "终端"],
     "ssh_operations"),
    # 文件操作
    (["文件", "读取", "写入", "复制", "移动", "删除文件", "目录"],
     "file_transfer"),
    # API集成
    (["api", "接口", "集成", "webhook", "REST"],
     "api_integration"),
    # 任务调度
    (["调度", "定时", "cron", "计划", "排程", "schedule"],
     "task_scheduling"),
    # GitHub推送
    (["github", "推送", "push", "git", "仓库", "repo", "提交代码"],
     "github_push"),
    # 升级更新
    (["升级", "更新", "upgrade", "update", "版本", "最新"],
     "ssh_operations"),  # 升级需要SSH到各机器执行
]


def extract_required_capability(task_description: str) -> list[str]:
    """从任务描述中提取所需能力

    Args:
        task_description: 任务描述文本

    Returns:
        匹配到的能力列表（按匹配度排序）
    """
    desc_lower = task_description.lower()
    matched: list[tuple[str, int]] = []  # (capability, match_count)

    for keywords, capability in KEYWORD_TO_CAPABILITY:
        count = sum(1 for kw in keywords if kw in desc_lower)
        if count > 0:
            matched.append((capability, count))

    # 按匹配数降序
    matched.sort(key=lambda x: x[1], reverse=True)
    return [cap for cap, _ in matched]


class DecisionEngine:
    """自主决策引擎

    分析任务需求，判断自己执行还是委派给其他Agent。

    使用方式:
        engine = DecisionEngine(
            agent_id="xiaoqing",
            capabilities=["code_generation", "web_search", ...],
        )
        decision = await engine.decide("帮我查服务器状态", client)
    """

    def __init__(self, agent_id: str, capabilities: list[str],
                 specialties: list[str] = None, description: str = ""):
        self.agent_id = agent_id
        self.capabilities = set(capabilities)
        self.specialties = specialties or []
        self.description = description

    def can_handle(self, capability: str) -> bool:
        """检查自己是否具备指定能力"""
        return capability in self.capabilities

    async def decide(self, task_description: str,
                     client=None) -> Decision:
        """分析任务并做出决策

        Args:
            task_description: 任务描述
            client: MeshClient实例，用于查询其他Agent能力（可选）

        Returns:
            Decision 决策结果
        """
        # 1. 提取所需能力
        required_caps = extract_required_capability(task_description)

        if not required_caps:
            # 无法从描述中提取明确能力，尝试通用匹配
            return self._default_decision()

        # 2. 优先检查最匹配的能力（第一个），如果自己没有就委派
        #    避免次要能力匹配导致错误地自己执行
        primary_cap = required_caps[0]
        if self.can_handle(primary_cap):
            log.info(f"✅ 决策: 自己执行 (能力: {primary_cap})")
            return Decision(
                decision=DecisionType.SELF,
                capability_needed=primary_cap,
                reason=f"自己具备 {primary_cap} 能力",
                confidence=0.9,
            )

        # 3. 主要能力自己没有，查找谁有
        target, alternatives = await self._find_capable_agent(primary_cap, client)

        if target:
            log.info(f"🔀 决策: 委派给 {target} (能力: {primary_cap})")
            return Decision(
                decision=DecisionType.DELEGATE,
                capability_needed=primary_cap,
                target_agent=target,
                reason=f"自己没有 {primary_cap}，{target} 具备该能力",
                confidence=0.85,
                alternatives=alternatives,
            )

        # 4. 找不到合适的目标，走默认流程
        log.warning(f"⚠️ 决策: 无法找到具备 {primary_cap} 的Agent")
        return Decision(
            decision=DecisionType.UNKNOWN,
            capability_needed=primary_cap,
            reason=f"找不到具备 {primary_cap} 的在线Agent",
            confidence=0.3,
        )

    def _default_decision(self) -> Decision:
        """无法提取能力时的默认决策 — 默认自己尝试执行"""
        return Decision(
            decision=DecisionType.SELF,
            reason="无法明确判断所需能力，默认自己尝试",
            confidence=0.4,
        )

    async def _find_capable_agent(self, capability: str,
                                  client=None) -> tuple[str, list[str]]:
        """查找具备指定能力的其他在线Agent

        Returns:
            (best_agent_id, [alternative_ids])
        """
        # 方式1: 通过HTTP API查询（推荐，有完整的在线状态）
        if client:
            try:
                data = await client.discover_remote(capability)
                if data and isinstance(data, dict):
                    agents = data.get("agents", data.get(capability, {}).get("agents", []))
                    if agents:
                        # 过滤掉自己
                        others = [a for a in agents if a != self.agent_id]
                        if others:
                            return others[0], others[1:]
            except Exception as e:
                log.warning(f"HTTP能力发现失败: {e}")

        # 方式2: 基于静态配置的硬编码映射（离线兜底）
        # 这是一个简单的后备方案，实际部署时依赖HTTP API
        fallback_map = {
            "system_monitor": ["xiaolan", "xiaobai"],
            "download_management": ["xiaobai"],
            "ssh_operations": ["xiaobai"],
            "data_analysis": ["xiaolan"],
            "api_integration": ["xiaolan"],
            "task_scheduling": ["xiaolan"],
            "code_generation": ["xiaolan", "xiaoqing"],
            "desktop_automation": ["xiaoqing"],
            "wechat_operations": ["xiaoqing"],
            "translation": ["xiaoqing"],
        }
        candidates = fallback_map.get(capability, [])
        others = [a for a in candidates if a != self.agent_id]
        if others:
            return others[0], others[1:]

        return "", []
