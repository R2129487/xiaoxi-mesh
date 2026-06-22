#!/usr/bin/env python3
"""测试从本机连接到阿里云的小希-Mesh服务"""
import asyncio, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import websockets
from auth import Auth
import yaml

async def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    a = Auth(cfg["auth"]["secret_key"])
    token = a.create_token("xiaoqing", "agent")

    print(f"连接阿里云 ws://101.37.231.143:8765 ...")
    async with websockets.connect(f"ws://101.37.231.143:8765/ws/xiaoqing?token={token}") as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        d = json.loads(raw)
        print(f"初始消息: type={d['type']}, data={d.get('data',{})}")

        await ws.send(json.dumps({"type": "send", "to": "broadcast", "content": "小青从Y7000连上阿里云了！"}))
        conf = await asyncio.wait_for(ws.recv(), timeout=5)
        c = json.loads(conf)
        print(f"发送确认: type={c['type']}, msg_id={c.get('data',{}).get('message_id','')[:12]}")
        print("✅ 外网WebSocket通信正常")

asyncio.run(main())
