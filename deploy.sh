#!/usr/bin/env bash
# 小希-Mesh 一键部署脚本
set -e

echo "=== 小希-Mesh 部署脚本 ==="

# 1. 安装依赖
echo "[1/4] 安装 Python 依赖..."
pip install -r requirements.txt -q

# 2. 创建数据目录
echo "[2/4] 创建数据目录..."
mkdir -p data logs

# 3. 生成默认管理员密码（首次）
if [ ! -f ".initialized" ]; then
    echo "[3/4] 首次初始化..."
    python3 -c "
import yaml
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)
if not cfg['admin']['password_hash']:
    import bcrypt
    pw = 'admin123'
    h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    cfg['admin']['password_hash'] = h
    with open('config.yaml', 'w') as f:
        yaml.dump(cfg, f)
    print(f'管理员密码已设置: admin / {pw}')
"
    touch .initialized
else:
    echo "[3/4] 已初始化，跳过"

# 4. 启动服务
echo "[4/4] 启动服务..."
python3 -c "
import asyncio
from storage import Storage
async def init():
    s = Storage()
    await s.init()
    print('数据库初始化完成')
asyncio.run(init())
"

echo ""
echo "=== 部署完成 ==="
echo "WebSocket: ws://$(hostname -I | awk '{print $1}'):8765"
echo "HTTP API:  http://$(hostname -I | awk '{print $1}'):8765"
echo "管理登录:  admin / admin123 (首次请修改)"
echo ""
echo "启动服务:  python3 server.py"
echo "后台运行:  nohup python3 server.py > logs/mesh.log 2>&1 &"
