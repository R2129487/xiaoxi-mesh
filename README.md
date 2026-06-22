# 🌐 小希-Mesh v0.1

> 让多个 AI Agent 通过 WebSocket 互联互通的协作网络框架

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/Version-v0.1.0-orange.svg)]()

---

## 📖 项目简介

**小希-Mesh** 是一个轻量级的 AI Agent 协作网络框架。它通过 WebSocket 实时通信 + HTTP REST API 管理，让分布在不同机器上的 AI 智能体能够：

- 🔗 **互相连接** — 通过统一的消息中转服务器实现实时通信
- 🎯 **能力发现** — 自动声明和发现其他智能体的能力
- 📋 **任务委派** — 根据能力匹配自动路由任务到最佳智能体
- 🤝 **同步调用** — 一个智能体可以同步调用另一个智能体的能力并等待结果
- 🔒 **权限控制** — RBAC 角色权限管理（admin / agent / external / readonly）
- 📊 **审计日志** — 记录所有关键操作，支持异常行为检测

### 架构概览

```
┌──────────────────────────────────────────────────────────┐
│                    小希-Mesh 服务端                        │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ WebSocket │  │ HTTP API │  │  协作引擎  │  │ 审计日志  │ │
│  │  实时通信  │  │  管理接口  │  │ 路由/委派  │  │  权限控制 │ │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘ │
│        │             │             │             │       │
│        └─────────────┴──────┬──────┴─────────────┘       │
│                             │                            │
│                      ┌──────┴──────┐                     │
│                      │  SQLite DB  │                     │
│                      └─────────────┘                     │
└──────────────────────────────────────────────────────────┘
         ▲              ▲              ▲
         │              │              │
    ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
    │ Agent A │   │ Agent B │   │ Agent C │
    │  (小青)  │   │  (小白)  │   │  (小蓝)  │
    │  本地PC  │   │  云服务器 │   │  云服务器 │
    └─────────┘   └─────────┘   └─────────┘
```

## ✨ 功能列表

| 功能 | 说明 |
|------|------|
| **智能体注册** | 自动注册、Token 认证、能力声明 |
| **实时消息** | WebSocket 双向通信、离线消息存储、广播 |
| **任务路由** | 基于能力评分的智能匹配（能力50分 + 关键词30分 + 专长10分 + 在线奖励5分） |
| **任务委派** | 创建 → 自动路由 → 分配 → 通知 → 完成，全流程管理 |
| **能力发现** | 能力矩阵、能力搜索、能力统计 |
| **同步调用** | `call_agent()` 同步等待其他智能体返回结果 |
| **权限控制** | RBAC 四级角色：admin / agent / external / readonly |
| **审计日志** | 操作记录、频率统计、异常检测 |
| **Token 管理** | JWT 生成、验证、撤销 |
| **Web 管理** | 内置静态文件服务，可挂载管理前端 |

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-username/xiaoxi-mesh.git
cd xiaoxi-mesh
```

### 2. 安装依赖

```bash
# 推荐使用虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 启动服务端

```bash
# 首次启动会自动初始化数据库
python3 server.py
```

服务默认监听：
- **WebSocket**: `ws://0.0.0.0:8765`
- **HTTP API**: `http://0.0.0.0:8765`

### 4. 注册并启动智能体

```bash
# 启动小青（本地 AI 助手）
python3 agent_runner.py --agent xiaoqing

# 启动小白（服务器助手）
python3 agent_runner.py --agent xiaobai

# 启动小蓝（管理员）
python3 agent_runner.py --agent xiaolan
```

首次启动会自动注册并获取 Token。

### 5. 测试跨智能体调用

```bash
# 从小青调用小蓝的系统监控能力
python3 agent_runner.py --agent xiaoqing --test-call
```

## 🔧 配置说明

编辑 `config.yaml`：

```yaml
server:
  host: "0.0.0.0"
  ws_port: 8765          # WebSocket 端口

auth:
  secret_key: "your-secret-key"  # ⚠️ 生产环境必须修改！
  token_expire_hours: 72         # Token 有效期

storage:
  db_path: "data/messenger.db"   # SQLite 数据库路径

limits:
  max_message_size: 1048576      # 最大消息 1MB
  max_connections: 50            # 最大连接数

admin:
  username: "admin"
  password_hash: ""              # 首次启动自动设置
```

### 自定义智能体

编辑 `agent_runner.py` 中的 `AGENT_CONFIGS`：

```python
AGENT_CONFIGS = {
    "my_agent": {
        "name": "我的智能体",
        "server": "ws://your-server:8765",
        "capabilities": ["code_review", "translation"],
        "specialties": ["代码审查", "翻译"],
        "description": "我的自定义智能体",
    },
}
```

## 📡 API 文档

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 管理员登录，返回 JWT Token |

### 智能体管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agents/register` | 注册智能体 |
| GET | `/api/agents` | 获取所有智能体列表 |
| GET | `/api/agents/{agent_id}` | 获取单个智能体信息 |
| DELETE | `/api/agents/{agent_id}` | 删除智能体 |
| POST | `/api/agents/{agent_id}/capabilities` | 更新智能体能力 |

### 消息

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/messages/{agent_id}` | 获取离线消息 |
| POST | `/api/messages/send` | HTTP 发送消息 |

### 任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tasks` | 创建任务（自动路由） |
| GET | `/api/tasks` | 获取任务列表 |
| GET | `/api/tasks/{task_id}` | 获取任务详情 |
| POST | `/api/tasks/{task_id}/update` | 更新任务状态 |
| POST | `/api/tasks/{task_id}/complete` | 完成任务 |
| POST | `/api/tasks/{task_id}/reassign` | 重新分配任务 |
| DELETE | `/api/tasks/{task_id}` | 删除任务 |

### 能力发现

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/capabilities` | 获取所有能力分布 |
| GET | `/api/capabilities/{capability}` | 获取具备某能力的智能体 |
| GET | `/api/capabilities/matrix/all` | 获取能力矩阵 |
| GET | `/api/capabilities/stats/overview` | 获取能力统计 |
| GET | `/api/capabilities/search/{query}` | 搜索能力 |

### 审计与统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/audit` | 获取审计日志 |
| GET | `/api/audit/recent` | 获取最近活动 |
| GET | `/api/stats` | 获取系统统计 |

### Token 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tokens/create?agent_id=xxx` | 为智能体生成 Token |
| POST | `/api/tokens/revoke/{token_id}` | 撤销 Token |

### WebSocket 协议

连接地址：`ws://server:8765/ws/{agent_id}?token={jwt_token}`

**发送消息：**
```json
{
  "type": "send",
  "to": "target_agent_id",
  "content": "你好",
  "data_type": "text"
}
```

**同步调用其他智能体：**
```json
{
  "type": "agent_call",
  "to": "target_agent_id",
  "call_id": "unique-call-id",
  "capability": "system_monitor",
  "params": {"action": "get_status"}
}
```

**更新能力：**
```json
{
  "type": "capability_update",
  "capabilities": ["code_review", "translation"],
  "specialties": ["Python", "Rust"]
}
```

## 📁 项目结构

```
xiaoxi-mesh/
├── server.py              # 主服务（WebSocket + HTTP API）
├── client.py              # 客户端 SDK
├── agent_runner.py        # 智能体接入脚本（开箱即用）
├── auth.py                # JWT 认证模块
├── permissions.py         # RBAC 权限控制
├── audit.py               # 审计日志
├── storage.py             # SQLite 数据存储层
├── models.py              # 数据模型（Pydantic）
├── config.yaml            # 配置文件
├── requirements.txt       # Python 依赖
├── deploy.sh              # 一键部署脚本
├── LICENSE                # MIT 许可证
├── README.md              # 项目文档
├── collaboration/         # 协作引擎
│   ├── __init__.py
│   ├── registry.py        # 智能体注册表
│   ├── router.py          # 任务路由器（能力评分匹配）
│   ├── delegator.py       # 任务委派器
│   └── discovery.py       # 能力发现服务
├── config/
│   └── capability_permissions.yaml
├── static/
│   ├── alpine.min.js      # Alpine.js（前端轻量框架）
│   └── tailwind.js        # Tailwind CSS
└── tests/
    ├── full_test.py       # 完整功能测试
    ├── test_integration.py # 集成测试
    ├── register_agents.py # 智能体注册脚本
    ├── test_remote.py     # 远程连接测试
    └── test_ws_live.py    # WebSocket 实时测试
```

## 🛠️ 技术栈

- **后端**: Python 3.10+ / FastAPI / Uvicorn
- **通信**: WebSocket (websockets) + HTTP REST API
- **数据库**: SQLite (aiosqlite)
- **认证**: JWT (PyJWT) + bcrypt
- **数据校验**: Pydantic v2
- **配置**: YAML

## 🤝 贡献指南

欢迎贡献！以下是参与方式：

1. **Fork** 本仓库
2. **创建特性分支**: `git checkout -b feature/amazing-feature`
3. **提交更改**: `git commit -m 'Add amazing feature'`
4. **推送分支**: `git push origin feature/amazing-feature`
5. **提交 Pull Request**

### 开发环境

```bash
# 安装开发依赖
pip install -r requirements.txt

# 运行测试
python3 tests/full_test.py

# 启动服务（开发模式）
uvicorn server:app --host 0.0.0.0 --port 8765 --reload
```

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

## 🔗 相关链接

- 项目主页: https://github.com/your-username/xiaoxi-mesh
- 问题反馈: https://github.com/your-username/xiaoxi-mesh/issues

---

**小希-Mesh** — 让 AI Agent 协作更简单 🤖✨
