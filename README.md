# 小希 (XiaoXi) — 多智能体协作系统

小希是一个轻量级的多智能体（Multi-Agent）协作框架，让多个 AI 智能体像团队一样协同工作。支持网页端和移动端访问。

## 项目结构

```
xiaoxi/
├── client/          # Web 前端（HTML/CSS/JS）
│   ├── chat.html    # 聊天界面
│   ├── agents.html  # 智能体管理
│   ├── config.html  # 系统配置
│   ├── memory.html  # 记忆管理
│   └── admin.html   # 调度管理面板
├── server/          # 后端服务（FastAPI Python）
│   ├── dispatcher.py       # 任务调度器主程序
│   ├── dispatcher_core.py  # 调度核心逻辑
│   ├── models.py           # 数据模型
│   ├── storage.py          # 本地存储（SQLite）
│   ├── routes/             # API 路由
│   │   ├── chat.py         # 聊天 API
│   │   ├── agents.py       # 智能体管理 API
│   │   ├── config.py       # 配置管理 API
│   │   ├── memory.py       # 记忆管理 API
│   │   └── tasks.py        # 任务管理 API
│   ├── web_*.py            # 内嵌 HTML 渲染（兼容器）
│   └── config.yaml         # 服务配置文件
└── app/             # Flutter 移动端
    ├── lib/
    │   ├── main.dart        # 入口
    │   ├── screens/         # 页面
    │   └── services/        # API 调用
    ├── android/
    └── pubspec.yaml
```

## 快速开始

### 启动后端服务

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 编辑 config.yaml 配置你的 API Key 和 MESH 服务器地址
# 然后启动
python3 dispatcher.py
```

### 访问 Web 界面

服务启动后，浏览器打开：

```
http://localhost:8767/chat      # 聊天
http://localhost:8767/agents    # 智能体管理
http://localhost:8767/config    # 系统配置
http://localhost:8767/memory    # 记忆管理
http://localhost:8767/admin     # 调度面板
```

### 编译移动端

```bash
cd app
flutter build apk --debug
```

## 核心概念

### 智能体 (Agent)

每个智能体是一个独立的 AI 角色，拥有：
- **身份**：名称、头像、颜色
- **能力**：描述它能干什么（如 `chat,code,search`）
- **连接方式**：本机、SSH 远程、MESH 协议
- **提示词**：定义性格和行为

### 任务调度 (Task Dispatcher)

调度器收到用户请求后：
1. 分析任务类型
2. 匹配最合适的智能体
3. 分派任务并跟踪进度
4. 汇总结果返回

### 记忆系统 (Memory)

持久化的键值对存储，智能体之间共享上下文信息。

## 技术栈

- **后端**：Python + FastAPI + aiosqlite
- **前端**：纯 HTML/CSS/JS（无框架依赖）
- **移动端**：Flutter (Dart)
- **通信**：WebSocket + REST API + MESH 协议
- **AI 模型**：兼容 OpenAI API 格式的任意大模型

## 架构图

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Web Client  │     │  Flutter App │     │  SSH Agents │
│  (浏览器)    │     │  (手机)      │     │  (远程)     │
└──────┬──────┘     └──────┬───────┘     └──────┬──────┘
       │                   │                    │
       └──────────┬────────┘────────────────────┘
                  │
         ┌────────▼────────┐
         │  Task Dispatcher │  ← 任务调度中心
         │  (FastAPI)      │
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │  MESH Network    │  ← 智能体通信网络
         └────────┬────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
┌───▼───┐   ┌────▼────┐   ┌───▼───┐
│ 小青   │   │ 小蓝    │   │ 小白  │
│ (本机) │   │ (阿里云) │   │ (新云) │
└───────┘   └─────────┘   └───────┘
```

## 配置说明

编辑 `server/config.yaml`：

```yaml
server:
  host: "0.0.0.0"
  port: 8767

dispatcher_agent:
  llm:
    provider: "mimo"
    base_url: "https://api.example.com/v1"
    api_key_path: "path/to/apikey.txt"
    model: "your-model"

mesh:
  host: "127.0.0.1"
  port: 8765
  admin_user: "admin"
  admin_password: "<PASSWORD>"
```

## License

MIT
