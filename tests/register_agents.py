#!/usr/bin/env python3
"""在阿里云上注册智能体并返回 token"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from auth import Auth
from storage import Storage
from models import Agent
import yaml
import asyncio

async def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    a = Auth(cfg["auth"]["secret_key"])
    store = Storage()
    await store.init()

    # 注册三个智能体
    agents = [
        ("xiaobai", "小白", "agent"),
        ("xiaoqing", "小青", "agent"),
        ("xiaolan", "小蓝", "admin"),
    ]
    for aid, name, role in agents:
        agent = Agent(agent_id=aid, name=name, role=role)
        ok = await store.register_agent(agent)
        if ok:
            token = a.create_token(aid, role)
            print(f"{name} ({aid}): {token}")
        else:
            token = a.create_token(aid, role)
            print(f"{name} ({aid}): [已存在] {token}")

asyncio.run(main())
