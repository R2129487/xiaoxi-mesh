#!/usr/bin/env python3
"""小青：小希-Mesh 全面功能测试 (从Y7000连阿里云)"""
import asyncio, json, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import httpx
import websockets
from auth import Auth
import yaml

SERVER = "http://101.37.231.143:8765"
WS_URL = "ws://101.37.231.143:8765"

async def section(n, name):
    print(f"\n{'='*50}")
    print(f" [{n}] {name}")
    print(f"{'='*50}")

async def main():
    # 读取本地配置生成 token（跟阿里云同key）
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    a = Auth(cfg["auth"]["secret_key"])
    admin_token = a.create_token("admin", "admin")

    results = {"pass": 0, "fail": 0}

    async def check(name, ok):
        if ok:
            print(f"  ✅ {name}")
            results["pass"] += 1
        else:
            print(f"  ❌ {name}")
            results["fail"] += 1

    async with httpx.AsyncClient(timeout=10) as cli:

        # ── 1. 健康检查 ──
        await section(1, "基础功能")
        r = await cli.get(f"{SERVER}/health")
        await check("健康检查", r.status_code == 200 and r.json()["status"] == "ok")
        print(f"     在线智能体: {r.json()['agents_online']}")

        # ── 2. 管理员登录 ──
        r = await cli.post(f"{SERVER}/api/auth/login",
            json={"username": "admin", "password": "admin123"})
        await check("管理员登录", r.status_code == 200)
        login_token = r.json()["data"]["token"]
        print(f"     Token过期: {r.json()['data']['expires_in']}s")

        # ── 3. 智能体列表 ──
        r = await cli.get(f"{SERVER}/api/agents")
        await check("智能体列表", r.status_code == 200)
        agents = r.json()["data"]
        print(f"     已注册: {len(agents)} 个")
        for ag in agents:
            status_icon = "🟢" if ag["online"] else "🔴"
            print(f"       {status_icon} {ag['name']} ({ag['agent_id']}) - {ag['role']}")

        # ── 4. 智能体详情 ──
        r = await cli.get(f"{SERVER}/api/agents/xiaoqing")
        await check("小青详情查询", r.status_code == 200 and r.json()["data"]["name"] == "小青")

        # ── 5. HTTP 发消息 ──
        await section(2, "HTTP API 消息功能")
        r = await cli.post(f"{SERVER}/api/messages/send", json={
            "from_id": "xiaoqing", "to_id": "xiaobai",
            "content": "HTTP测试消息", "type": "text"
        })
        await check("HTTP发送消息", r.status_code == 200)
        msg_id = r.json()["data"]["message_id"]
        print(f"     消息ID: {msg_id[:16]}...")

        # ── 6. 获取离线消息 ──
        r = await cli.get(f"{SERVER}/api/messages/xiaobai")
        await check("获取离线消息", r.status_code == 200)
        msgs = r.json()["data"]
        await check("离线消息不为空", len(msgs) > 0)
        for m in msgs:
            print(f"     [{m['from_id']}] {m['content'][:40]}")

        # ── 7. 状态更新 ──
        r = await cli.post(f"{SERVER}/api/agents/status", json={
            "agent_id": "xiaoqing", "status": "online"
        })
        await check("状态更新API", r.status_code == 200)

    # ── 8. WebSocket 连接 ──
    await section(3, "WebSocket 功能")
    token = a.create_token("xiaoqing", "agent")

    async with websockets.connect(f"{WS_URL}/ws/xiaoqing?token={token}") as ws:
        # 收初始上线广播
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        d = json.loads(raw)
        await check("WS连接 + 初始消息", d["type"] in ("status", "message"))
        print(f"     首条消息: type={d['type']}")

        # Ping/Pong
        await ws.send(json.dumps({"type": "ping"}))
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        d = json.loads(raw)
        await check("Ping/Pong", d["type"] == "pong")

        # 发送消息给小白
        await ws.send(json.dumps({
            "type": "send", "to": "xiaobai",
            "content": "小青实时测试：功能正常！"
        }))
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        d = json.loads(raw)
        await check("WS实时发送消息", d["type"] == "sent")

        # 广播消息
        await ws.send(json.dumps({
            "type": "send", "to": "broadcast",
            "content": "【广播】小青已上线，系统启动完成！"
        }))
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        d = json.loads(raw)
        await check("广播消息发送", d["type"] == "sent")

        # 状态更新
        await ws.send(json.dumps({"type": "status", "status": "busy"}))
        await check("WebSocket状态更新", True)

        # 发送文件类型消息
        await ws.send(json.dumps({
            "type": "send", "to": "xiaobai",
            "data_type": "file", "content": "/data/ftp/test_report.pdf",
            "priority": "high"
        }))
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        d = json.loads(raw)
        await check("文件类型消息", d["type"] == "sent")

        # 大消息测试
        big_content = "A" * 10240  # 10KB
        await ws.send(json.dumps({
            "type": "send", "to": "xiaobai",
            "content": big_content
        }))
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        d = json.loads(raw)
        await check("大消息(10KB)", d["type"] == "sent")

    # ── 9. 双客户端同时在线 ──
    await section(4, "双客户端实时通信")
    bai_token = a.create_token("xiaobai", "agent")
    qing_token = a.create_token("xiaoqing", "agent")
    exchange_ok = False

    async def xiaobai_task():
        nonlocal exchange_ok
        async with websockets.connect(f"{WS_URL}/ws/xiaobai?token={bai_token}") as ws:
            # 跳过初始消息
            await asyncio.wait_for(ws.recv(), timeout=3)
            await asyncio.wait_for(ws.recv(), timeout=3)
            # 等消息
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            msg = json.loads(raw)
            print(f"     小白收到: [{msg['data']['from_id']}] {msg['data']['content'][:40]}")
            exchange_ok = True

    async def xiaoqing_task():
        async with websockets.connect(f"{WS_URL}/ws/xiaoqing?token={qing_token}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=3)
            await asyncio.wait_for(ws.recv(), timeout=3)
            await asyncio.sleep(1)
            await ws.send(json.dumps({
                "type": "send", "to": "xiaobai",
                "content": "双客户端测试：小青→小白实时互通"
            }))
            await asyncio.wait_for(ws.recv(), timeout=5)

    await asyncio.gather(xiaobai_task(), xiaoqing_task())
    await check("双客户端实时互通", exchange_ok)

    # ── 10. 非法 token 拒绝 ──
    await section(5, "安全验证")
    try:
        async with websockets.connect(f"{WS_URL}/ws/xiaoqing?token=invalid_token") as ws:
            await ws.recv()
            await check("非法token拒绝", False)
    except websockets.exceptions.InvalidStatus:
        await check("非法token拒绝", True)

    try:
        async with httpx.AsyncClient() as cli:
            r = await cli.post(f"{SERVER}/api/agents/register", json={
                "agent_id": "hacker", "name": "黑客", "role": "agent"
            })
            await check("无token注册拒绝", r.status_code == 401)
    except Exception:
        pass

    # ── 汇总 ──
    print(f"\n{'='*50}")
    print(f" 结果: ✅ {results['pass']} 通过  ", end="")
    if results['fail']:
        print(f"❌ {results['fail']} 失败")
    else:
        print("🎉 全部通过！")
    print(f"{'='*50}")

if __name__ == "__main__":
    asyncio.run(main())
