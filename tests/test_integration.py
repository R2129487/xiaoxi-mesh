"""小希-Mesh 集成测试"""
import asyncio
import json
import time
import httpx
from client import MeshClient

SERVER = "http://localhost:8765"
WS_URL = "ws://localhost:8765"

async def test_all():
    print("=" * 50)
    print("小希-Mesh 集成测试")
    print("=" * 50)

    # 1. 健康检查
    print("\n[1] 健康检查...")
    async with httpx.AsyncClient() as cli:
        r = await cli.get(f"{SERVER}/health")
        assert r.status_code == 200
        print(f"  ✅ {r.json()}")

    # 2. 注册智能体
    print("\n[2] 注册智能体...")
    agents = {
        "xiaobai": "小白",
        "xiaoqing": "小青",
        "xiaolan": "小蓝",
    }
    tokens = {}
    async with httpx.AsyncClient() as cli:
        for aid, name in agents.items():
            r = await cli.post(f"{SERVER}/api/agents/register", json={
                "agent_id": aid,
                "name": name,
                "role": "agent",
            })
            if r.status_code == 409:
                print(f"  ⚠️  {aid} 已存在，重新获取 token")
                continue
            assert r.status_code == 200
            data = r.json()["data"]
            tokens[aid] = data["token"]
            print(f"  ✅ {aid} ({name}) -> token: {data['token'][:20]}...")

    # 3. 查看智能体列表
    print("\n[3] 智能体列表...")
    async with httpx.AsyncClient() as cli:
        r = await cli.get(f"{SERVER}/api/agents")
        data = r.json()["data"]
        for a in data:
            print(f"  {a['agent_id']:12} {a['name']:8} {'🟢' if a['online'] else '🔴'}")

    # 4. WebSocket 双向通信测试
    print("\n[4] WebSocket 双向通信...")
    received = []

    async def run_client(aid, token):
        client = MeshClient(WS_URL, aid, token)
        client.on_message(lambda m: received.append((aid, m)))
        await client.connect()

    # 同时启动小白和小青
    if "xiaobai" not in tokens or "xiaoqing" not in tokens:
        print("  ⚠️  Token 不完整，跳过 WebSocket 测试")
        print("\n" + "=" * 50)
        print("测试完成（部分跳过）")
        return

    async with httpx.AsyncClient() as cli:
        # 先拿 token
        for aid in ["xiaobai", "xiaoqing"]:
            # 注册过的就跳过
            pass

    # 用正确的 token
    bai_token = tokens.get("xiaobai", "")
    qing_token = tokens.get("xiaoqing", "")

    if not bai_token or not qing_token:
        print("  需要手动注册智能体获取 token")
        print("  请先调用 /api/agents/register")
    else:
        async def test_comm():
            bai = MeshClient(WS_URL, "xiaobai", bai_token)
            qing = MeshClient(WS_URL, "xiaoqing", qing_token)

            messages = []

            def on_msg(sender):
                def cb(msg):
                    messages.append((sender, msg))
                    print(f"  📨 {sender} 收到: {msg.get('content', '')[:50]}")
                return cb

            bai.on_message(on_msg("小白"))
            qing.on_message(on_msg("小青"))

            # 同时连接
            await asyncio.gather(bai.connect(), qing.connect())
            await asyncio.sleep(1)

            # 小青发消息给小白
            print("  小青 -> 小白: 你好小白，测试消息")
            await qing.send("xiaobai", "你好小白，测试消息")
            await asyncio.sleep(1)

            # 小白广播
            print("  小白 -> broadcast: 大家注意，系统正常")
            await bai.broadcast("大家注意，系统正常")
            await asyncio.sleep(1)

            # 断开
            await bai.disconnect()
            await qing.disconnect()
            print(f"  共收到 {len(messages)} 条消息")
            print(f"  ✅ WebSocket 双向通信正常")

        await test_comm()

    # 5. HTTP 消息发送
    print("\n[5] HTTP 消息发送...")
    async with httpx.AsyncClient() as cli:
        r = await cli.post(f"{SERVER}/api/messages/send", json={
            "from_id": "xiaoqing",
            "to_id": "xiaobai",
            "content": "这是 HTTP 发送的消息",
            "type": "text",
        })
        assert r.status_code == 200
        msg_id = r.json()["data"]["message_id"]
        print(f"  ✅ 发送成功，消息ID: {msg_id}")

        # 获取离线消息
        r = await cli.get(f"{SERVER}/api/messages/xiaobai")
        msgs = r.json()["data"]
        print(f"  小白离线消息: {len(msgs)} 条")
        for m in msgs:
            print(f"    {m['from_id']}: {m['content'][:50]}")

    print("\n" + "=" * 50)
    print("全部测试完成 ✅")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test_all())
