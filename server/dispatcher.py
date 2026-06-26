"""
任务调度器 - FastAPI 主入口
独立服务，监听 8767 端口
"""

from __future__ import annotations

import os
import sys
import json
import yaml
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage import Storage
from dispatcher_core import DispatcherCore
from models import Agent, TaskLog
from web_ui import get_web_html
from web_chat import get_chat_html
from web_config import get_config_html
from web_memory import get_memory_html
from web_agents import get_agents_html

# ==================== MESH 客户端 ====================

class MeshClient:
    """MESH 服务客户端，负责连接 MESH 并注册为 task-dispatcher"""

    def __init__(self, mesh_config: dict):
        self.host = mesh_config.get("host", "127.0.0.1")
        self.port = mesh_config.get("port", 8765)
        self.admin_user = mesh_config.get("admin_user", "admin")
        self.admin_password = mesh_config.get("admin_password", "<PASSWORD>")
        self.agent_id = mesh_config.get("agent_id", "task-dispatcher")
        self.capabilities = mesh_config.get("capabilities", [])
        self._token = None
        self._ws = None
        self._running = False
        self._keepalive_task = None
        self._receive_task = None
        self._pending_replies: dict[str, asyncio.Future] = {}

    async def send_to_agent(self, agent_id: str, content: str, timeout: float = 60) -> str | None:
        """通过 MESH 给指定智能体发消息，等待回复"""
        if not self._ws or not self._running:
            return None

        import uuid
        call_id = str(uuid.uuid4())[:8]
        future = asyncio.get_event_loop().create_future()
        self._pending_replies[call_id] = {"future": future, "expected_from": agent_id}

        await self._send({
            "type": "send",
            "to": agent_id,
            "data_type": "text",
            "content": content,
        })

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_replies.pop(call_id, None)
            return None

    async def connect(self):
        """连接 MESH：登录 → 创建token → WS 连接 → 注册在线"""
        import httpx
        import websockets

        try:
            # 1. 登录 MESH 获取 admin token
            login_url = f"http://{self.host}:{self.port}/api/auth/login"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(login_url, json={
                    "username": self.admin_user,
                    "password": self.admin_password,
                })
                if resp.status_code != 200:
                    print(f"[MeshClient] MESH 登录失败: {resp.status_code} {resp.text}")
                    return False
                data = resp.json()
                admin_token = data.get("token") or data.get("data", {}).get("token", "")
                if not admin_token:
                    print(f"[MeshClient] MESH 登录返回无 token: {data}")
                    return False
                print(f"[MeshClient] MESH 登录成功, admin_token 获取成功")

            # 2. 用 admin token 为 task-dispatcher 创建专用 token
            async with httpx.AsyncClient(timeout=10) as client:
                token_resp = await client.post(
                    f"http://{self.host}:{self.port}/api/tokens/create?agent_id={self.agent_id}&role=agent",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                if token_resp.status_code != 200:
                    print(f"[MeshClient] 创建专用 token 失败: {token_resp.status_code}")
                    # 如果 /api/tokens/create 不可用，直接用 admin token
                    self._token = admin_token
                else:
                    td = token_resp.json()
                    self._token = td.get("token") or td.get("data", {}).get("token", admin_token)
                print(f"[MeshClient] 获取到 task-dispatcher token")

            # 2. 通过 WebSocket 连接 MESH
            ws_url = f"ws://{self.host}:{self.port}/ws/{self.agent_id}?token={self._token}"
            self._ws = await websockets.connect(ws_url)
            print(f"[MeshClient] WebSocket 已连接: {ws_url}")

            # 3. 注册 capabilities
            if self.capabilities:
                await self._send({
                    "type": "capability_update",
                    "capabilities": self.capabilities,
                    "specialties": ["任务调度", "任务管理", "任务跟踪", "任务分配"],
                })

            # 4. 启动消息接收循环和心跳
            self._running = True
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            self._receive_task = asyncio.create_task(self._receive_loop())

            print(f"[MeshClient] task-dispatcher 已在 MESH 上线")
            return True

        except Exception as e:
            print(f"[MeshClient] MESH 连接失败: {e}")
            self._token = None
            self._ws = None
            return False

    async def disconnect(self):
        """断开 MESH 连接"""
        self._running = False
        for task in [self._keepalive_task, self._receive_task]:
            if task:
                task.cancel()
        self._keepalive_task = None
        self._receive_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        print("[MeshClient] MESH 连接已断开")

    async def _send(self, data: dict):
        """发送 JSON 消息到 MESH"""
        if self._ws:
            try:
                await self._ws.send(json.dumps(data, ensure_ascii=False))
            except Exception as e:
                print(f"[MeshClient] 发送失败: {e}")

    async def _keepalive_loop(self):
        """心跳保活循环"""
        while self._running:
            await asyncio.sleep(30)
            try:
                await self._send({"type": "ping"})
            except Exception:
                print("[MeshClient] 心跳发送失败，尝试重连...")
                self._ws = None
                self._running = False
                break

    async def _receive_loop(self):
        """消息接收循环：处理来自 MESH 的转发消息"""
        import httpx

        while self._running and self._ws:
            try:
                raw = await self._ws.recv()
                data = json.loads(raw)
                msg_type = data.get("type", "")
                msg_data = data.get("data", data)

                if msg_type == "ping":
                    await self._send({"type": "pong"})
                elif msg_type == "pong":
                    pass
                elif msg_type == "message":
                    # 收到转发来的消息
                    content = msg_data.get("content", "")
                    from_id = msg_data.get("from_id", "")

                    # 检查是否是对 pending 请求的回复
                    matched = False
                    for cid, info in list(self._pending_replies.items()):
                        if info["expected_from"] == from_id:
                            future = self._pending_replies.pop(cid)["future"]
                            if not future.done():
                                future.set_result(content)
                            matched = True
                            break

                    if not matched and content:
                        print(f"[MeshClient] 收到来自 {from_id} 的消息：{content[:50]}")
                        await self._create_task_from_content(content, from_id)
                elif msg_type == "task_request":
                    # 直接的任务请求
                    task_info = msg_data if isinstance(msg_data, dict) else {}
                    title = task_info.get("title", task_info.get("description", "未知任务"))
                    description = task_info.get("description", "")
                    print(f"[MeshClient] 收到任务请求：{title}")
                    await self._create_task_from_content(description or title, msg_data.get("from_agent", "unknown"))
            except json.JSONDecodeError:
                continue
            except Exception as e:
                if self._running:
                    print(f"[MeshClient] 接收消息出错: {e}")
                    await asyncio.sleep(1)
                break

    async def _create_task_from_content(self, content: str, from_id: str):
        """通过本地 REST API 创建任务"""
        import httpx

        try:
            api_url = f"http://127.0.0.1:{config['server']['port']}/api/tasks"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(api_url, json={
                    "title": content[:50],
                    "description": content,
                    "priority": "medium",
                    "required_skills": "",
                })
                if resp.status_code == 200:
                    result = resp.json()
                    task_id = result.get("data", {}).get("id", "")
                    print(f"[MeshClient] 任务已创建: {task_id}")
                    # 通过 MESH 回复创建结果
                    await self._send({
                        "type": "send",
                        "to": from_id if from_id != "unknown" else "admin",
                        "data_type": "text",
                        "content": f"✅ 任务已创建（ID: {task_id}）：{content[:50]}",
                    })
                else:
                    print(f"[MeshClient] 创建任务失败: {resp.status_code}")
        except Exception as e:
            print(f"[MeshClient] 创建任务异常: {e}")


mesh_client = None
mesh_remote_client = None

# ==================== 配置加载 ====================

def load_config() -> dict:
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    default_config = {
        "server": {
            "host": "0.0.0.0",
            "port": 8767,
        },
        "database": {
            "path": "data/dispatcher.db",
        },
        "tasks": {
            "default_timeout": 300,
            "max_retries": 3,
            "retry_delay": 60,
        },
        "agents": {
            "heartbeat_interval": 30,
            "offline_threshold": 90,
            "max_load": 10,
        },
    }
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if loaded:
                # 递归合并配置
                def merge(base, override):
                    for k, v in override.items():
                        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                            merge(base[k], v)
                        else:
                            base[k] = v
                merge(default_config, loaded)
    return default_config


config = load_config()

# ==================== 全局实例 ====================

storage = Storage(db_path=os.path.join(os.path.dirname(__file__), config["database"]["path"]))
dispatcher_core = DispatcherCore(storage, config)


# ==================== 生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global mesh_client, mesh_remote_client
    # 启动时：初始化数据库和预注册智能体
    print("[Dispatcher] 初始化数据库...")
    await storage.init_db()
    print("[Dispatcher] 数据库初始化完成")

    # 注入全局引用到路由模块
    import routes.tasks as tasks_route
    import routes.agents as agents_route
    import routes.chat as chat_route
    tasks_route.storage = storage
    tasks_route.dispatcher_core = dispatcher_core
    agents_route.storage = storage
    chat_route.config = config
    chat_route.storage = storage
    chat_route.dispatcher_core = dispatcher_core
    # 预注册已知智能体
    print("[Dispatcher] 预注册智能体...")
    await _register_default_agents()

    # 连接本地 MESH
    mesh_client = MeshClient(config["mesh"])
    if await mesh_client.connect():
        print("[Dispatcher] ✓ 本地 MESH 连接成功")
    else:
        print("[Dispatcher] ⚠ 本地 MESH 连接失败（不影响本地运行）")

    # 注入MESH客户端到路由模块
    chat_route.mesh_client = mesh_client

    # 注入存储到记忆路由
    import routes.memory as memory_route
    memory_route.storage = storage

    # 预填默认记忆（各智能体职责）
    print("[Dispatcher] 初始化记忆...")
    default_memories = [
        ("agent:xiaolan:role", "小蓝是阿里云服务器管理员，负责网站管理(xixisz.top系列)、安全中心(fail2ban/防火墙)、阿里云服务器运维。他是系统管理员和安全负责人。", "agent", "阿里云,网站,安全"),
        ("agent:xiaobai:role", "小白是新云服务器管理员，负责新云运维、下载站管理、GitHub推送、FTP服务维护。他是新云和下载中心的管理员。", "agent", "新云,下载,GitHub,FTP"),
        ("agent:xiaohei:role", "小黑是手工房资料管理员和知识库管理员，负责希希手作加工部的资料管理、知识库维护、商品图片和文档管理。", "agent", "手工房,知识库,资料"),
        ("agent:xiaoqing:role", "小青是本机(Y7000)助手，负责本地文件操作、桌面自动化、微信操作、本地开发(Flutter编译/代码)。她是本地事务处理者。", "agent", "本地,桌面,微信,开发"),
        ("rule:task:disk", "查磁盘空间/磁盘使用情况：先问用户是哪台机器。Y7000→小青，新云→小白，阿里云→小蓝。", "rule", "磁盘,查询,分配"),
        ("rule:task:website", "网站相关(xixisz.top)：直接分配给负责网站管理的小蓝。", "rule", "网站,分配"),
        ("rule:task:download", "下载/上传相关：分配给负责下载站管理的小白。", "rule", "下载,上传,分配"),
        ("rule:task:handcraft", "手工房/希希手作相关：分配给负责手工房资料管理的小黑。", "rule", "手工房,希希手作,分配"),
        ("rule:task:security", "安全相关(fail2ban/防火墙/入侵检测)：分配给安全负责人小蓝。", "rule", "安全,防火墙,分配"),
        ("rule:task:knowledge", "知识库相关：分配给知识库管理员小黑。", "rule", "知识库,分配"),
        ("rule:general:clarify", "如果用户请求不明确(比如只说'查磁盘'不说哪台机器)，先追问清楚再分配。", "rule", "追问,澄清"),
    ]
    for key, value, category, tags in default_memories:
        try:
            existing = await storage.get_memory(key=key)
            if not existing:
                await storage.set_memory(key, value, category, tags)
        except Exception:
            pass
    print(f"[Dispatcher] 已初始化 {len(default_memories)} 条记忆")

    print(f"[Dispatcher] 任务调度器启动完成，监听端口 {config['server']['port']}")
    yield
    # 关闭时：清理资源
    print("[Dispatcher] 正在关闭...")
    if mesh_client:
        await mesh_client.disconnect()
    if mesh_remote_client:
        await mesh_remote_client.disconnect()
    await storage.close()
    print("[Dispatcher] 已关闭")


async def _register_default_agents():
    """预注册默认智能体（小青/小蓝/小白）"""
    default_agents = [
        Agent(
            id="xiao-qing",
            name="小青",
            capabilities="chat,code,analyze,write,search",
            status="online",
            max_load=config["agents"]["max_load"],
            current_load=0,
            connection_type="local",
            host=None, port=None, ssh_user=None,
            command_template="hermes -z '{task}' --yolo",
        ),
        Agent(
            id="xiao-lan",
            name="小蓝",
            capabilities="chat,code,test,deploy,translate",
            status="online",
            max_load=config["agents"]["max_load"],
            current_load=0,
            connection_type="ssh",
            host="<SERVER_IP>", port=<SSH_PORT>, ssh_user="<SSH_USER>",
            command_template="hermes -z '{task}' --yolo",
        ),
        Agent(
            id="xiao-bai",
            name="小白",
            capabilities="chat,analyze,search,image,write",
            status="online",
            max_load=config["agents"]["max_load"],
            current_load=0,
            connection_type="ssh",
            host="<SERVER_IP>", port=<SSH_PORT>, ssh_user="<SSH_USER>",
            command_template="hermes -z '{task}' --yolo",
        ),
        Agent(
            id="xiao-hei",
            name="小黑",
            capabilities="knowledge,doc,image,file",
            status="online",
            max_load=config["agents"]["max_load"],
            current_load=0,
            connection_type="ssh",
            host="<SERVER_IP>", port=<SSH_PORT>, ssh_user="<SSH_USER>",
            command_template="hermes -z '{task}' --yolo",
        ),
    ]
    for agent in default_agents:
        existing = await storage.get_agent(agent.id)
        if not existing:
            await storage.create_agent(agent)
            print(f"  ✓ 注册智能体: {agent.name} ({agent.id})")
            await storage.add_log(TaskLog(
                task_id="system",
                agent_id=agent.id,
                action="register",
                details=f"预注册智能体：{agent.name}，能力：{agent.capabilities}"
            ))
        else:
            # 更新状态为在线
            await storage.update_agent(agent.id, {
                "status": "online",
                "last_seen": __import__("models").now_str(),
            })
            print(f"  ✓ 智能体已存在: {agent.name} ({agent.id})")


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="Task Dispatcher",
    description="任务调度器 - 小希Mesh智能体任务调度服务",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 路由注册 ====================

# Web UI — 直接跳转到聊天
@app.get("/", response_class=RedirectResponse)
async def index():
    return "/chat"


# 调度管理面板（原首页内容）
@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """返回调度管理面板"""
    return get_web_html()


# 调度员聊天界面
@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    """返回调度员聊天界面"""
    return get_chat_html()


# 调度员配置页面
@app.get("/config", response_class=HTMLResponse)
async def config_page():
    """返回调度员配置界面"""
    return get_config_html()


# 调度员记忆管理页面
@app.get("/memory", response_class=HTMLResponse)
async def memory_page():
    """返回记忆管理界面"""
    return get_memory_html()


# 智能体管理页面
@app.get("/agents", response_class=HTMLResponse)
async def agents_page():
    """返回智能体管理界面"""
    return get_agents_html()


# API 状态
@app.get("/api/status")
async def api_status():
    """API 状态检查"""
    return {
        "code": 0,
        "message": "Task Dispatcher 运行中",
        "version": "1.0.0",
    }


# 统计数据
@app.get("/api/stats")
async def get_stats():
    """获取系统统计"""
    try:
        stats = await storage.get_stats()
        return {"code": 0, "data": stats}
    except Exception as e:
        return {"code": 1, "message": str(e)}


# 日志
@app.get("/api/logs")
async def get_logs(task_id: str = None, limit: int = 100):
    """获取日志"""
    try:
        logs = await storage.get_logs(task_id=task_id, limit=limit)
        return {"code": 0, "data": [l.model_dump() for l in logs]}
    except Exception as e:
        return {"code": 1, "message": str(e)}


# 注册子路由
from routes.tasks import router as tasks_router
from routes.agents import router as agents_router
from routes.chat import router as chat_router
from routes.config import router as config_router
from routes.memory import router as memory_router
app.include_router(tasks_router)
app.include_router(agents_router)
app.include_router(chat_router)
app.include_router(config_router)
app.include_router(memory_router)

# ==================== 文件上传 ====================

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 挂载静态文件服务
app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.post("/api/chat/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传文件，返回可访问的 URL"""
    import uuid
    ext = os.path.splitext(file.filename or "file")[1] or ""
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    save_path = os.path.join(UPLOAD_DIR, safe_name)
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    file_url = f"/static/uploads/{safe_name}"
    return {
        "code": 0,
        "data": {
            "url": file_url,
            "name": file.filename or safe_name,
            "size": len(content),
        },
    }


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    host = config["server"]["host"]
    port = config["server"]["port"]
    print(f"\n{'='*50}")
    print(f"  Task Dispatcher 任务调度器")
    print(f"  地址: http://{host}:{port}")
    print(f"  API:  http://{host}:{port}/api/tasks")
    print(f"{'='*50}\n")
    uvicorn.run("dispatcher:app", host=host, port=port, reload=False, log_level="info")
