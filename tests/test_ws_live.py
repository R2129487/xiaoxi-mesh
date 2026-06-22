#!/usr/bin/env python3
"""快速测试：小希-Mesh WebSocket 双向通信"""
import asyncio, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import websockets
from auth import Auth
import yaml

async def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    a = Auth(cfg["auth"]["secret_key"])

    bai_token = a.create_token("xiaobai", "agent")
    qing_token = a.create_token("xiaoqing", "agent")

    delivered = []

    async def xiaobai():
        async with websockets.connect(f"ws://localhost:8765/ws/xiaobai?token={bai_token}") as ws:
            # 跳过初始消息
            await asyncio.wait_for(ws.recv(), timeout=2)
            await asyncio.wait_for(ws.recv(), timeout=2)
            print("[小白] 等待消息...")
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(raw)
            content = msg["data"]["content"]
            sender = msg["data"]["from_id"]
            print(f"[小白] 收到来自 [{sender}] 的消息: {content}")
            delivered.append(("bai_recv", content))

    async def xiaoqing():
        async with websockets.connect(f"ws://localhost:8765/ws/xiaoqing?token={qing_token}") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2)
            await asyncio.wait_for(ws.recv(), timeout=2)
            await asyncio.sleep(1.5)
            await ws.send(json.dumps({
                "type": "send", "to": "xiaobai",
                "content": "小青 -> 小白：实时消息测试通过！"
            }))
            conf = await asyncio.wait_for(ws.recv(), timeout=3)
            j = json.loads(conf)
            print(f"[小青] 发送确认: type={j['type']}")
            delivered.append(("qing_send", j["type"]))

    await asyncio.gather(xiaobai(), xiaoqing())
    ok = len(delivered) == 2 and delivered[1][1] == "sent"
    print(f"\n{'✅ 双向实时通信测试通过' if ok else '❌ 测试失败'}")
    sys.exit(0 if ok else 1)

asyncio.run(main())
