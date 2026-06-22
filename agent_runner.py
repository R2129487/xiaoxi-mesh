#!/usr/bin/env python3
"""小希-Mesh 智能体接入脚本

每台机器运行此脚本即可自动连接到消息中转服务器。
支持同步跨智能体调用、能力处理器注册。

用法:
    python3 agent_runner.py --agent xiaoqing
    python3 agent_runner.py --agent xiaobai
    python3 agent_runner.py --agent xiaolan
    python3 agent_runner.py --agent xiaoqing --test-call  # 测试跨智能体调用
"""
import argparse
import asyncio
import json
import logging
import signal
import sys
import os

# 把当前目录加到路径，以便导入 client 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client import MeshClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("agent")

# ── 各智能体配置 ──

AGENT_CONFIGS = {
    "xiaoqing": {
        "name": "小青",
        "server": "ws://101.37.231.143:8765",
        "capabilities": [
            "code_generation", "file_transfer", "web_search",
            "translation", "desktop_automation", "wechat_operations"
        ],
        "specialties": ["编程开发", "文件管理", "网络搜索", "桌面自动化", "微信操作"],
        "description": "本机(Y7000)AI助手，擅长编程、文件管理、桌面自动化、微信消息处理",
    },
    "xiaobai": {
        "name": "小白",
        "server": "ws://101.37.231.143:8765",
        "capabilities": [
            "file_transfer", "system_monitor", "download_management",
            "ssh_operations", "web_search"
        ],
        "specialties": ["文件下载", "系统监控", "服务器运维", "下载站管理"],
        "description": "新云服务器AI助手，擅长文件处理、下载站管理、系统监控",
    },
    "xiaolan": {
        "name": "小蓝",
        "server": "ws://101.37.231.143:8765",
        "capabilities": [
            "system_monitor", "web_search", "code_generation",
            "data_analysis", "api_integration", "task_scheduling"
        ],
        "specialties": ["系统管理", "数据分析", "API集成", "任务调度"],
        "description": "阿里云服务器管理员，7x24在线，负责协调调度",
    },
}


class AgentRunner:
    """智能体运行器 - 自动连接、注册能力、处理消息、支持同步调用"""

    def __init__(self, agent_id: str, token: str = None):
        if agent_id not in AGENT_CONFIGS:
            raise ValueError(f"未知智能体: {agent_id}，可选: {list(AGENT_CONFIGS.keys())}")

        cfg = AGENT_CONFIGS[agent_id]
        self.agent_id = agent_id
        self.name = cfg["name"]
        self.server_http = cfg["server"].replace("ws://", "http://").replace("wss://", "https://")
        self.server_ws = cfg["server"]
        self.token = token
        self.capabilities = cfg["capabilities"]
        self.specialties = cfg["specialties"]
        self.description = cfg["description"]
        self._running = False
        self.client = None

    def register_handler(self, capability: str, handler, public: bool = False):
        """注册能力处理器

        当其他智能体调用本智能体的某个能力时，自动执行对应的处理器。

        Args:
            capability: 能力名称
            handler: 异步处理函数，签名: async def handler(params: dict) -> dict
        """
        if self.client:
            self.client.register_handler(capability, handler, public=public)
        else:
            log.warning(f"客户端未初始化，无法注册处理器: {capability}")

    async def _ensure_token(self):
        """确保有可用的 token：先尝试注册，已存在则用 admin 获取新 token"""
        if self.token:
            return

        import httpx
        async with httpx.AsyncClient(timeout=10) as http:
            # 1. 尝试注册（首次会成功并返回 token）
            try:
                r = await http.post(f"{self.server_http}/api/agents/register", json={
                    "agent_id": self.agent_id,
                    "name": self.name,
                    "role": "agent",
                    "capabilities": self.capabilities,
                    "specialties": self.specialties,
                    "description": self.description,
                })
                if r.status_code == 200:
                    data = r.json()
                    self.token = data.get("data", {}).get("token", "")
                    if self.token:
                        log.info(f"✅ 注册成功，已获取 token")
                        return
            except Exception as e:
                log.warning(f"注册失败: {e}")

            # 2. 已注册，用 admin 登录获取新 token
            log.info(f"智能体已存在，用 admin 获取 token...")
            try:
                r = await http.post(f"{self.server_http}/api/auth/login", json={
                    "username": "admin", "password": "admin123"
                })
                admin_token = r.json().get("data", {}).get("token", "")
                if not admin_token:
                    log.error("admin 登录失败")
                    return

                # 用 admin token 为智能体生成新 token
                r = await http.post(
                    f"{self.server_http}/api/tokens/create",
                    params={"agent_id": self.agent_id, "role": "agent"},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                if r.status_code == 200:
                    self.token = r.json().get("data", {}).get("token", "")
                    log.info(f"✅ 已获取新 token")
                else:
                    log.error(f"获取 token 失败: {r.status_code} {r.text[:100]}")
            except Exception as e:
                log.error(f"获取 token 异常: {e}")

    async def start(self):
        """启动智能体"""
        log.info(f"🚀 {self.name} 启动中...")

        # 确保有 token
        await self._ensure_token()
        if not self.token:
            log.error(f"❌ {self.name} 无法获取 token，退出")
            return

        # 创建客户端
        self.client = MeshClient(
            server_url=self.server_ws,
            agent_id=self.agent_id,
            token=self.token,
        )
        self.client.set_capabilities(self.capabilities, self.specialties)

        log.info(f"   能力: {', '.join(self.capabilities)}")

        # 设置回调
        self.client.on_message(self._handle_message)
        self.client.on_status(self._handle_status)
        self.client.on_agent_call(self._handle_agent_call)

        # 注册默认的能力处理器
        self._register_default_handlers()

        # 连接并注册
        self._running = True
        try:
            await self.client.connect()
            log.info(f"✅ {self.name} 已连接到消息服务器")

            # 保持运行
            while self._running:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            log.info(f"⏹ {self.name} 收到停止信号")
        except Exception as e:
            log.error(f"❌ {self.name} 异常: {e}")
        finally:
            await self.stop()

    def _register_default_handlers(self):
        """注册默认能力处理器（子类可覆盖）"""
        # 通用能力
        self.register_handler("echo", self._handle_echo, public=True)
        self.register_handler("system_monitor", self._handle_system_monitor, public=True)

    async def _handle_echo(self, params: dict) -> dict:
        """Echo 测试处理器"""
        return {"message": f"Echo from {self.name}", "params_received": params}

    async def _handle_system_monitor(self, params: dict) -> dict:
        """系统监控处理器"""
        import platform, os
        action = params.get("action", "get_status")
        if action == "get_status":
            # 获取基本系统信息
            try:
                import psutil
                cpu = f"{psutil.cpu_percent(interval=1)}%"
                mem = psutil.virtual_memory()
                mem_info = f"{mem.percent}% ({mem.used // (1024**3):.1f}GB/{mem.total // (1024**3):.1f}GB)"
                disk = psutil.disk_usage("/")
                disk_info = f"{disk.percent}% ({disk.used // (1024**3):.1f}GB/{disk.total // (1024**3):.1f}GB)"
            except ImportError:
                # 没有psutil，用基本方法
                cpu = "N/A (psutil未安装)"
                mem_info = "N/A"
                disk_info = "N/A"
            return {
                "agent": self.name,
                "hostname": platform.node(),
                "platform": platform.platform(),
                "cpu": cpu,
                "memory": mem_info,
                "disk": disk_info,
                "uptime": os.popen("uptime -p 2>/dev/null || echo N/A").read().strip(),
            }
        return {"error": f"未知action: {action}"}

    async def stop(self):
        """停止智能体"""
        self._running = False
        if self.client:
            await self.client.disconnect()
        log.info(f"👋 {self.name} 已断开连接")

    async def _handle_message(self, msg: dict):
        """处理收到的消息"""
        msg_type = msg.get("type", "unknown")
        from_id = msg.get("from", "unknown")
        content = msg.get("content", "")

        if msg_type == "ping":
            return  # 心跳忽略

        log.info(f"📩 收到消息 [{msg_type}] 来自 {from_id}: {content[:100]}")

        # 根据消息类型处理
        if msg_type == "task":
            await self._handle_task(msg)
        elif msg_type == "agent_call":
            await self._handle_agent_call(msg)
        elif msg_type == "text":
            await self._handle_text(msg)
        else:
            log.info(f"   未处理的消息类型: {msg_type}")

    async def _handle_task(self, msg: dict):
        """处理任务委派"""
        task_id = msg.get("metadata", {}).get("task_id", "unknown")
        content = msg.get("content", "")
        log.info(f"📋 收到任务 [{task_id}]: {content}")

        # TODO: 这里接入实际的任务执行逻辑
        # 目前先回复收到
        await self.client.send(msg.get("from", ""), f"收到任务，正在处理...", "text")

    async def _handle_agent_call(self, msg: dict):
        """处理跨智能体调用（兼容旧式和新式）"""
        from_id = msg.get("from_id", msg.get("from", ""))
        call_id = msg.get("call_id", "")
        capability = msg.get("capability", "")
        params = msg.get("params", {})
        content = msg.get("content", "")

        if capability:
            # 新式调用：基于 capability + params
            log.info(f"📞 收到调用请求: {from_id} -> {capability}({json.dumps(params, ensure_ascii=False)[:100]})")

            # 尝试查找已注册的处理器
            if capability in self.client._capability_handlers:
                try:
                    handler = self.client._capability_handlers[capability]
                    result = await handler(params)
                    if call_id:
                        await self.client.respond_to_call(call_id, data=result)
                except Exception as e:
                    log.error(f"能力 {capability} 执行异常: {e}")
                    if call_id:
                        await self.client.respond_to_call(call_id, error=str(e))
            else:
                log.warning(f"未找到能力处理器: {capability}")
                if call_id:
                    await self.client.respond_to_call(call_id, error=f"能力 {capability} 不支持")
        else:
            # 旧式调用：基于 content 文本
            action = content
            params_legacy = msg.get("metadata", {}).get("params", {})
            log.info(f"📞 收到旧式调用请求: {action}({json.dumps(params_legacy, ensure_ascii=False)[:100]})")

            # TODO: 这里接入实际的能力执行逻辑
            await self.client.send(from_id, f"调用 {action} 完成", "text")

    async def _handle_text(self, msg: dict):
        """处理普通文本消息"""
        from_id = msg.get("from", "")
        content = msg.get("content", "")
        log.info(f"💬 [{from_id}]: {content}")

    def _handle_status(self, data: dict):
        """处理状态变更"""
        agent_id = data.get("agent_id", "")
        status = data.get("status", "")
        log.info(f"🔄 状态变更: {agent_id} -> {status}")


async def _test_cross_agent_call(agent_id: str, token: str = None):
    """测试跨智能体同步调用"""
    log.info(f"🧪 开始测试跨智能体同步调用...")

    runner = AgentRunner(agent_id, token)
    await runner._ensure_token()
    if not runner.token:
        log.error("❌ 无法获取 token，测试终止")
        return

    client = MeshClient(
        server_url=runner.server_ws,
        agent_id=runner.agent_id,
        token=runner.token,
    )
    client.set_capabilities(runner.capabilities, runner.specialties)

    # 在后台运行连接
    connect_task = asyncio.create_task(client.connect())
    await asyncio.sleep(3)  # 等待连接建立

    if not client.ws:
        log.error("❌ 无法连接到消息服务器")
        connect_task.cancel()
        return

    try:
        # 测试 1: 调用 xiaolan 的 system_monitor 能力
        log.info("─── 测试 1: 调用小蓝的 system_monitor 能力 ───")
        try:
            result = await client.call_agent(
                target_id="xiaolan",
                capability="system_monitor",
                params={"action": "get_status"},
                timeout=15
            )
            log.info(f"✅ 调用成功: {result}")
        except TimeoutError as e:
            log.warning(f"⏰ 超时（小蓝可能未在线）: {e}")
        except RuntimeError as e:
            log.warning(f"⚠️ 调用失败: {e}")

        # 测试 2: 调用 xiaobai 的 system_monitor 能力
        log.info("─── 测试 2: 调用小白的 system_monitor 能力 ───")
        try:
            result = await client.call_agent(
                target_id="xiaobai",
                capability="system_monitor",
                params={"action": "get_load"},
                timeout=15
            )
            log.info(f"✅ 调用成功: {result}")
        except TimeoutError as e:
            log.warning(f"⏰ 超时（小白可能未在线）: {e}")
        except RuntimeError as e:
            log.warning(f"⚠️ 调用失败: {e}")

        # 测试 3: 调用不存在的能力
        log.info("─── 测试 3: 调用不存在的能力 ───")
        try:
            result = await client.call_agent(
                target_id="xiaolan",
                capability="nonexistent_ability",
                params={},
                timeout=10
            )
            log.info(f"✅ 调用成功: {result}")
        except TimeoutError as e:
            log.warning(f"⏰ 超时: {e}")
        except RuntimeError as e:
            log.warning(f"⚠️ 调用失败（预期）: {e}")

    finally:
        await client.disconnect()
        connect_task.cancel()
        log.info("🧪 测试完成")


def main():
    parser = argparse.ArgumentParser(description="小希-Mesh 智能体接入脚本")
    parser.add_argument("--agent", "-a", required=True,
                        choices=list(AGENT_CONFIGS.keys()),
                        help="智能体ID")
    parser.add_argument("--token", "-t", default=None,
                        help="认证Token（不提供则尝试注册获取）")
    parser.add_argument("--list", "-l", action="store_true",
                        help="列出所有可用智能体")
    parser.add_argument("--test-call", action="store_true",
                        help="测试跨智能体同步调用")
    args = parser.parse_args()

    if args.list:
        print("可用智能体:")
        for aid, cfg in AGENT_CONFIGS.items():
            print(f"  {aid}: {cfg['name']} - {cfg['description']}")
            print(f"       能力: {', '.join(cfg['capabilities'])}")
        return

    if args.test_call:
        # 测试模式
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_test_cross_agent_call(args.agent, args.token))
        except KeyboardInterrupt:
            pass
        finally:
            loop.close()
        return

    runner = AgentRunner(args.agent, args.token)

    # 优雅关闭
    loop = asyncio.new_event_loop()

    def shutdown_handler():
        loop.create_task(runner.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            pass  # Windows 不支持

    try:
        loop.run_until_complete(runner.start())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
