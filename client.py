"""小希-Mesh v2 客户端 SDK

各智能体通过此 SDK 接入消息中转服务，支持能力声明、任务请求、智能体互相调用。
新增：同步跨智能体调用（call_agent 同步等待响应）。

用法:
    client = MeshClient("ws://101.37.231.143:8765", "xiaoqing", "your-token")
    client.set_capabilities(["code_review", "translation"], ["python", "rust"])
    await client.connect()
    await client.send("xiaobai", "你好小白")
    await client.request_task("帮我审查这段代码")
    # 同步调用其他智能体
    result = await client.call_agent("xiaolan", "system_monitor", {"action": "get_status"})
"""
from __future__ import annotations
import asyncio
import json
import logging
import uuid
import httpx
from typing import Callable, Optional, Any

import websockets

log = logging.getLogger("xiaoxi-mesh-client")


class MeshClient:
    def __init__(self, server_url: str, agent_id: str, token: str):
        """初始化客户端

        Args:
            server_url: 服务器地址 (如 http://101.37.231.143:8765)
            agent_id: 智能体 ID
            token: JWT Token
        """
        self.server_url = server_url.rstrip("/")
        self.agent_id = agent_id
        self.token = token
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._on_message: Optional[Callable] = None
        self._on_status: Optional[Callable] = None
        self._on_task: Optional[Callable] = None
        self._on_agent_call: Optional[Callable] = None
        self._on_capability_update: Optional[Callable] = None
        self._capabilities: list[str] = []
        self._specialties: list[str] = []
        # ── 同步调用相关 ──
        self._pending_calls: dict[str, asyncio.Event] = {}  # call_id -> Event
        self._call_results: dict[str, dict] = {}  # call_id -> result dict
        self._capability_handlers: dict[str, Callable] = {}
        self._public_capabilities: list[str] = []  # capability -> async handler

    # ── 事件回调 ──

    def on_message(self, callback: Callable):
        """收到消息回调: callback(msg: dict)"""
        self._on_message = callback
        return self

    def on_status(self, callback: Callable):
        """状态变更回调: callback(data: dict)"""
        self._on_status = callback
        return self

    def on_task(self, callback: Callable):
        """收到任务回调: callback(data: dict)"""
        self._on_task = callback
        return self

    def on_agent_call(self, callback: Callable):
        """收到智能体调用回调: callback(data: dict)"""
        self._on_agent_call = callback
        return self

    def on_capability_update(self, callback: Callable):
        """能力更新回调: callback(data: dict)"""
        self._on_capability_update = callback
        return self

    # ── 能力管理 ──

    def set_capabilities(self, capabilities: list[str], specialties: list[str] = None):
        """设置自身能力（连接后自动上报）"""
        self._capabilities = capabilities
        self._specialties = specialties or []

    async def update_capabilities(self, capabilities: list[str],
                                   specialties: list[str] = None):
        """运行时更新能力"""
        self._capabilities = capabilities
        if specialties is not None:
            self._specialties = specialties
        if self.ws:
            await self.ws.send(json.dumps({
                "type": "capability_update",
                "capabilities": self._capabilities,
                "specialties": self._specialties,
                "public_capabilities": self._public_capabilities,
            }))

    async def discover_capabilities(self, query: str = ""):
        """查询能力

        Args:
            query: 搜索关键词，空字符串返回全部能力矩阵
        """
        if not self.ws:
            log.warning("未连接")
            return None
        await self.ws.send(json.dumps({
            "type": "discover",
            "query": query,
        }))

    # ── 任务相关 ──

    async def request_task(self, description: str,
                           required_capabilities: list[str] = None,
                           target: str = "auto"):
        """请求任务（自动路由或指定目标）

        Args:
            description: 任务描述
            required_capabilities: 需要的能力
            target: 目标智能体 ID，"auto" 表示自动路由
        """
        if not self.ws:
            log.warning("未连接")
            return
        await self.ws.send(json.dumps({
            "type": "task",
            "to": target,
            "description": description,
            "required_capabilities": required_capabilities or [],
        }))

    async def update_task_status(self, task_id: str, status: str = "",
                                  result: str = ""):
        """更新任务状态"""
        if not self.ws:
            return
        data = {"type": "task_update", "task_id": task_id}
        if status:
            data["status"] = status
        if result:
            data["result"] = result
        await self.ws.send(json.dumps(data))

    async def complete_task(self, task_id: str, result: str = ""):
        """完成任务"""
        await self.update_task_status(task_id, "completed", result)

    # ── 智能体互相调用（同步） ──

    def register_handler(self, capability: str, handler: Callable, public: bool = False):
        """注册能力处理器

        当其他智能体调用本智能体的某个能力时，自动执行对应的处理器。

        Args:
            capability: 能力名称
            handler: 异步处理函数，签名: async def handler(params: dict) -> dict
        """
        self._capability_handlers[capability] = handler
        log.info(f"[{self.agent_id}] 已注册能力处理器: {capability}")

    async def call_agent(self, target_id: str, capability: str,
                         params: dict = None, timeout: float = 30) -> dict:
        """同步调用其他智能体的能力

        发送请求后阻塞等待目标智能体的响应。

        Args:
            target_id: 目标智能体 ID
            capability: 目标能力名称
            params: 调用参数
            timeout: 超时时间（秒）

        Returns:
            目标智能体返回的结果字典

        Raises:
            TimeoutError: 超时未收到响应
            RuntimeError: 目标智能体返回错误
        """
        if not self.ws:
            raise RuntimeError("未连接到消息服务器")

        call_id = str(uuid.uuid4())[:12]
        params = params or {}

        # 创建同步事件
        event = asyncio.Event()
        self._pending_calls[call_id] = event
        self._call_results[call_id] = {}

        # 发送调用请求
        await self.ws.send(json.dumps({
            "type": "agent_call",
            "to": target_id,
            "call_id": call_id,
            "capability": capability,
            "params": params,
            "content": f"调用能力: {capability}",  # 保持向后兼容
        }))
        log.info(f"[{self.agent_id}] 同步调用 {target_id}.{capability}，等待响应...")

        # 等待响应
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_calls.pop(call_id, None)
            self._call_results.pop(call_id, None)
            raise TimeoutError(f"调用 {target_id}.{capability} 超时（{timeout}秒）")

        # 获取结果
        result = self._call_results.pop(call_id, {})
        self._pending_calls.pop(call_id, None)

        if result.get("error"):
            raise RuntimeError(f"调用 {target_id}.{capability} 失败: {result['error']}")

        return result.get("data", result)

    async def respond_to_call(self, call_id: str, data: Any = None,
                               error: str = None):
        """响应其他智能体的调用请求

        Args:
            call_id: 调用 ID（从收到的 agent_call 消息中获取）
            data: 返回数据
            error: 错误信息（如果处理失败）
        """
        if not self.ws:
            log.warning("未连接，无法发送响应")
            return

        response = {
            "type": "agent_call_response",
            "call_id": call_id,
            "data": data,
            "error": error,
        }
        await self.ws.send(json.dumps(response))
        log.info(f"[{self.agent_id}] 已发送调用响应: call_id={call_id}")

    # ── HTTP API 方法 ──

    async def query_task(self, task_id: str) -> Optional[dict]:
        """通过 HTTP 查询任务详情"""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.server_url}/api/tasks/{task_id}",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            data = resp.json()
            return data.get("data") if data.get("success") else None

    async def list_tasks(self, status: str = None) -> list[dict]:
        """通过 HTTP 查询任务列表"""
        url = f"{self.server_url}/api/tasks"
        if status:
            url += f"?status={status}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {self.token}"})
            data = resp.json()
            return data.get("data", []) if data.get("success") else []

    async def discover_remote(self, query: str = "") -> dict:
        """通过 HTTP 查询能力"""
        url = f"{self.server_url}/api/capabilities"
        if query:
            url = f"{self.server_url}/api/capabilities/search/{query}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {self.token}"})
            data = resp.json()
            return data.get("data", {}) if data.get("success") else {}

    # ── 连接管理 ──

    async def connect(self):
        """连接到消息服务器（自动重连，连接后自动上报能力）"""
        uri = f"{self.server_url}/ws/{self.agent_id}?token={self.token}"
        self._running = True
        reconnect_delay = 5
        max_delay = 120
        while self._running:
            try:
                self.ws = await websockets.connect(uri, ping_interval=30)
                reconnect_delay = 5  # 连接成功，重置退避
                log.info(f"[{self.agent_id}] 已连接到消息服务器")

                # 连接后自动上报能力
                if self._capabilities:
                    await self.update_capabilities(self._capabilities, self._specialties)

                await self._listen()
            except (websockets.ConnectionClosed, OSError) as e:
                if self._running:
                    log.warning(f"[{self.agent_id}] 连接断开，{reconnect_delay}秒后重连: {e}")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_delay)
            except Exception as e:
                log.error(f"[{self.agent_id}] 连接异常: {e}")
                if self._running:
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_delay)

    async def disconnect(self):
        """断开连接"""
        self._running = False
        if self.ws:
            await self.ws.close()
            self.ws = None

    # ── 消息收发 ──

    async def send(self, to: str, content: str, msg_type: str = "text",
                   priority: str = "normal", reply_to: Optional[str] = None):
        """发送消息给指定智能体或 broadcast"""
        if not self.ws:
            log.warning("未连接，消息未发送")
            return None
        payload = {
            "type": "send",
            "to": to,
            "content": content,
            "data_type": msg_type,
            "priority": priority,
        }
        if reply_to:
            payload["reply_to"] = reply_to
        await self.ws.send(json.dumps(payload))

    async def broadcast(self, content: str, msg_type: str = "text"):
        """广播消息"""
        await self.send("broadcast", content, msg_type)

    async def update_status(self, status: str = "online",
                            message: Optional[str] = None):
        """更新在线状态"""
        if not self.ws:
            return
        payload = {"type": "status", "status": status}
        if message:
            payload["message"] = message
        await self.ws.send(json.dumps(payload))

    # ── 内部 ──

    async def _listen(self):
        """消息监听循环"""
        async for raw in self.ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")

            if msg_type == "pong":
                continue

            elif msg_type == "message":
                msg_data = data.get("data", {})
                log.info(f"[{self.agent_id}] 收到来自 {msg_data.get('from_id')} 的消息")
                if self._on_message:
                    await self._safe_call(self._on_message, msg_data)

            elif msg_type == "status":
                status_data = data.get("data", {})
                if self._on_status:
                    await self._safe_call(self._on_status, status_data)

            elif msg_type == "task":
                task_data = data.get("data", {})
                log.info(f"[{self.agent_id}] 收到任务: {task_data.get('task_id')}")
                if self._on_task:
                    await self._safe_call(self._on_task, task_data)

            elif msg_type == "agent_call_response":
                # ── 同步调用响应处理 ──
                call_id = data.get("call_id", "")
                if call_id in self._pending_calls:
                    self._call_results[call_id] = {
                        "data": data.get("data"),
                        "error": data.get("error"),
                    }
                    self._pending_calls[call_id].set()
                    log.info(f"[{self.agent_id}] 收到调用响应: call_id={call_id}")
                else:
                    log.warning(f"[{self.agent_id}] 收到未知调用响应: call_id={call_id}")

            elif msg_type == "agent_call":
                call_data = data.get("data", {})
                from_id = call_data.get("from_id", "")
                call_id = call_data.get("call_id", "")
                capability = call_data.get("capability", "")
                params = call_data.get("params", {})
                content = call_data.get("content", "")
                log.info(f"[{self.agent_id}] 收到来自 {from_id} 的调用: {capability or content}")

                # 尝试自动执行已注册的能力处理器
                if capability and capability in self._capability_handlers:
                    try:
                        handler = self._capability_handlers[capability]
                        result = await handler(params)
                        # 自动发送响应
                        if call_id:
                            await self.respond_to_call(call_id, data=result)
                    except Exception as e:
                        log.error(f"[{self.agent_id}] 能力处理器 {capability} 异常: {e}")
                        if call_id:
                            await self.respond_to_call(call_id, error=str(e))
                else:
                    # 交给回调处理（保持向后兼容）
                    if self._on_agent_call:
                        await self._safe_call(self._on_agent_call, call_data)

            elif msg_type == "capability_update":
                cap_data = data.get("data", {})
                if self._on_capability_update:
                    await self._safe_call(self._on_capability_update, cap_data)

            elif msg_type == "discovery_result":
                result_data = data.get("data", [])
                log.info(f"[{self.agent_id}] 能力发现结果: {len(result_data)} 条")

            elif msg_type == "error":
                log.warning(f"[{self.agent_id}] 服务端错误: {data.get('message')}")

            elif msg_type in ("sent", "task_created", "task_updated", "call_sent"):
                pass  # 确认消息，静默处理

    async def _safe_call(self, callback, *args):
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            log.error(f"回调异常: {e}")
