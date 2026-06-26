"""
任务调度器 - 核心调度逻辑模块
负责任务分析、智能体匹配、任务分派、进度跟踪和失败处理
"""

import random
import asyncio
from typing import Optional
from models import Task, Agent, TaskLog, now_str
from storage import Storage


# 关键词 → 能力映射表（纯规则匹配）
SKILL_KEYWORDS = {
    "聊天": "chat",
    "对话": "chat",
    "问答": "chat",
    "客服": "chat",
    "代码": "code",
    "编程": "code",
    "开发": "code",
    "写代码": "code",
    "修复": "code",
    "调试": "code",
    "搜索": "search",
    "查找": "search",
    "查询": "search",
    "搜索文件": "search",
    "分析": "analyze",
    "分析数据": "analyze",
    "统计": "analyze",
    "数据分析": "analyze",
    "报告": "analyze",
    "翻译": "translate",
    "翻译成": "translate",
    "写文档": "write",
    "文档": "write",
    "写作": "write",
    "文章": "write",
    "测试": "test",
    "测试代码": "test",
    "单元测试": "test",
    "部署": "deploy",
    "发布": "deploy",
    "上线": "deploy",
    "图片": "image",
    "图像": "image",
    "生成图片": "image",
    "设计": "image",
}


class DispatcherCore:
    """调度器核心逻辑"""

    def __init__(self, storage: Storage, config: dict):
        self.storage = storage
        self.config = config

    def analyze_task(self, task: Task) -> list[str]:
        """
        分析任务内容，识别所需能力
        纯规则匹配，不需要 LLM
        """
        text = f"{task.title} {task.description}".lower()
        found_skills = set()

        for keyword, skill in SKILL_KEYWORDS.items():
            if keyword in text:
                found_skills.add(skill)

        # 如果任务已指定 required_skills，也解析进去
        if task.required_skills:
            for s in task.required_skills.split(","):
                s = s.strip().lower()
                if s:
                    found_skills.add(s)

        return list(found_skills) if found_skills else ["chat"]  # 默认需要聊天能力

    def find_best_agent(self, required_skills: list[str], agents: list[Agent]) -> Optional[Agent]:
        """
        根据能力匹配和负载均衡，找到最佳智能体
        策略：先找能力匹配的，再按负载从低到高排序
        """
        if not agents:
            return None

        # 只考虑在线的智能体
        online_agents = [a for a in agents if a.status in ("online", "busy")]

        # 计算每个智能体的能力匹配分
        scored_agents = []
        for agent in online_agents:
            agent_caps = agent.capabilities.lower().split(",") if agent.capabilities else []
            agent_caps = [c.strip() for c in agent_caps]

            # 计算匹配得分
            match_score = 0
            for skill in required_skills:
                if skill in agent_caps:
                    match_score += 2  # 精确匹配得2分
                # 部分匹配
                for ac in agent_caps:
                    if skill in ac or ac in skill:
                        match_score += 1
                        break

            # 负载惩罚（负载越高扣分越多）
            load_penalty = agent.current_load / max(agent.max_load, 1)

            final_score = match_score - load_penalty
            if match_score > 0 or not required_skills:  # 有匹配或没有技能要求
                scored_agents.append((final_score, agent))

        if not scored_agents:
            # 如果没找到匹配的，就选负载最低的在线智能体
            if online_agents:
                return min(online_agents, key=lambda a: a.current_load)
            return None

        # 按分数降序排列，同分时选负载低的
        scored_agents.sort(key=lambda x: (-x[0], x[1].current_load))
        return scored_agents[0][1]

    async def dispatch(self, task: Task, agent: Agent) -> Task:
        """
        分派任务给智能体
        更新任务状态和智能体负载
        """
        task.assigned_to = agent.id
        task.status = "running"
        task.started_at = now_str()

        # 更新任务
        await self.storage.update_task(task.id, {
            "assigned_to": agent.id,
            "status": "running",
            "started_at": task.started_at,
        })

        # 更新智能体负载
        agent.current_load += 1
        if agent.current_load >= agent.max_load:
            agent.status = "busy"
        else:
            agent.status = "online"
        await self.storage.update_agent(agent.id, {
            "current_load": agent.current_load,
            "status": agent.status,
            "last_seen": now_str(),
        })

        # 记录日志
        await self.storage.add_log(TaskLog(
            task_id=task.id,
            agent_id=agent.id,
            action="dispatch",
            details=f"任务分派给 {agent.name}（{agent.id}），所需能力：{task.required_skills or '自动分析'}"
        ))

        return task

    async def auto_dispatch(self, task: Task) -> Task:
        """
        自动分派：分析任务 → 找最佳智能体 → 分派
        """
        # 1. 分析任务
        required_skills = self.analyze_task(task)

        # 如果任务没有指定 skills，更新上去
        if not task.required_skills:
            task.required_skills = ",".join(required_skills)
            await self.storage.update_task(task.id, {"required_skills": task.required_skills})

        # 更新任务状态为分析中
        task.status = "analyzing"
        await self.storage.update_task(task.id, {"status": "analyzing"})

        await self.storage.add_log(TaskLog(
            task_id=task.id,
            action="analyze",
            details=f"任务分析完成，所需能力：{', '.join(required_skills)}"
        ))

        # 2. 查找最佳智能体
        agents = await self.storage.get_agents()
        best_agent = self.find_best_agent(required_skills, agents)

        if not best_agent:
            # 没有可用智能体，任务排队等待
            task.status = "queued"
            await self.storage.update_task(task.id, {"status": "queued"})
            await self.storage.add_log(TaskLog(
                task_id=task.id,
                action="queued",
                details="没有可用智能体，任务进入排队等待"
            ))
            return task

        # 3. 分派任务
        task = await self.dispatch(task, best_agent)

        # 4. 模拟执行（在实际场景中，这是异步等待智能体返回结果）
        # 这里开一个后台任务模拟执行
        asyncio.create_task(self._simulate_execution(task.id))

        return task

    async def _simulate_execution(self, task_id: str):
        """
        模拟任务执行（实际场景中由智能体回调通知结果）
        等待几秒后完成
        """
        await asyncio.sleep(5)
        task = await self.storage.get_task(task_id)
        if not task or task.status != "running":
            return

        # 模拟执行成功
        await self.storage.update_task(task_id, {
            "status": "completed",
            "completed_at": now_str(),
            "result": f"任务 {task.title} 执行完成",
        })

        # 减少智能体负载
        if task.assigned_to:
            agent = await self.storage.get_agent(task.assigned_to)
            if agent:
                agent.current_load = max(0, agent.current_load - 1)
                await self.storage.update_agent(agent.id, {
                    "current_load": agent.current_load,
                    "status": "online" if agent.current_load < agent.max_load else "busy",
                })

        await self.storage.add_log(TaskLog(
            task_id=task_id,
            agent_id=task.assigned_to,
            action="completed",
            details="模拟任务执行完成"
        ))

    async def handle_failure(self, task_id: str, error: str):
        """
        处理任务失败
        根据配置决定是否重试
        """
        task = await self.storage.get_task(task_id)
        if not task:
            return

        max_retries = self.config.get("tasks", {}).get("max_retries", 3)
        retry_delay = self.config.get("tasks", {}).get("retry_delay", 60)

        task.retry_count = (task.retry_count or 0) + 1
        await self.storage.update_task(task_id, {
            "error": error,
            "retry_count": task.retry_count,
        })

        await self.storage.add_log(TaskLog(
            task_id=task_id,
            agent_id=task.assigned_to,
            action="failed",
            details=f"任务执行失败：{error}（第 {task.retry_count} 次重试）"
        ))

        if task.retry_count <= max_retries:
            # 重试：重新分派
            await self.storage.update_task(task_id, {"status": "queued"})
            await asyncio.sleep(retry_delay)
            await self.auto_dispatch(task)
        else:
            # 超过重试次数，标记为失败
            await self.storage.update_task(task_id, {
                "status": "failed",
                "completed_at": now_str(),
            })

    async def track_progress(self, task_id: str) -> dict:
        """
        跟踪任务进度
        返回任务的当前状态和执行信息
        """
        task = await self.storage.get_task(task_id)
        if not task:
            return {"error": "任务不存在"}

        logs = await self.storage.get_logs(task_id, limit=20)

        return {
            "task_id": task.id,
            "title": task.title,
            "status": task.status,
            "assigned_to": task.assigned_to,
            "priority": task.priority,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "result": task.result,
            "error": task.error,
            "retry_count": task.retry_count,
            "logs": [l.model_dump() for l in logs],
        }
