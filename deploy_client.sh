#!/usr/bin/env bash
# 小希-Mesh 客户端部署脚本
# 用法: bash deploy_client.sh --agent xiaohei --token <jwt_token> [--server 10.10.0.10:8765]
set -e

# ── 参数解析 ──
AGENT=""
TOKEN=""
SERVER_HOST="10.10.0.10"
SERVER_PORT="8765"

while [[ $# -gt 0 ]]; do
    case $1 in
        --agent) AGENT="$2"; shift 2 ;;
        --token) TOKEN="$2"; shift 2 ;;
        --server) SERVER_HOST="${2%%:*}"; SERVER_PORT="${2##*:}"; shift 2 ;;
        -h|--help)
            echo "用法: bash deploy_client.sh --agent <agent_id> --token <jwt_token> [--server host:port]"
            echo ""
            echo "  agent_id: xiaoqing | xiaobai | xiaolan | xiaohei"
            echo "  server:   mesh服务器地址 (默认 10.10.0.10:8765)"
            exit 0
            ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

if [[ -z "$AGENT" ]]; then
    echo "❌ 必须指定 --agent <agent_id>"
    exit 1
fi

# 验证 agent_id 合法
VALID_AGENTS="xiaoqing xiaobai xiaolan xiaohei"
if ! echo "$VALID_AGENTS" | grep -qw "$AGENT"; then
    echo "❌ 无效的 agent_id: $AGENT"
    echo "   可选: $VALID_AGENTS"
    exit 1
fi

echo "=== 小希-Mesh 客户端部署 ==="
echo "  智能体: $AGENT"
echo "  服务器: $SERVER_HOST:$SERVER_PORT"
echo ""

# ── 1. 检查 Python 环境 ──
echo "[1/6] 检查 Python 环境..."
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装"
    exit 1
fi
PYTHON_VER=$(python3 --version 2>&1)
echo "   $PYTHON_VER"

# ── 2. 创建工作目录 ──
echo "[2/6] 创建工作目录..."
DEPLOY_DIR="$HOME/xiaoxi-mesh"
mkdir -p "$DEPLOY_DIR"
echo "   $DEPLOY_DIR"

# ── 3. 检查/创建 venv ──
echo "[3/6] 检查 Python 虚拟环境..."
HERMES_DIR="$HOME/hermes-agent"
if [[ ! -d "$HERMES_DIR/venv" ]]; then
    echo "   创建 venv..."
    python3 -m venv "$HERMES_DIR/venv"
fi
# 确保 hermes CLI 可用
if [[ ! -f "$HERMES_DIR/venv/bin/hermes" ]]; then
    echo "   ⚠️  hermes CLI 未安装，agent_call 执行器可能不可用"
    echo "   请手动安装: cd $HERMES_DIR && pip install -e ."
fi
echo "   venv: $HERMES_DIR/venv"

# ── 4. 同步源代码 ──
echo "[4/6] 同步源代码..."
# 复制客户端必需文件
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 优先从 GitHub 拉取，失败则从本地复制
if command -v git &>/dev/null && git ls-remote https://github.com/R2129487/xiaoxi-mesh.git &>/dev/null 2>&1; then
    echo "   从 GitHub 同步..."
    cd "$DEPLOY_DIR"
    if [[ ! -d .git ]]; then
        git clone https://github.com/R2129487/xiaoxi-mesh.git temp_repo
        mv temp_repo/.git .
        mv temp_repo/* . 2>/dev/null || true
        rm -rf temp_repo
    else
        git pull --quiet
    fi
else
    echo "   从本地复制..."
    for f in agent_runner.py client.py executors.py decision_engine.py; do
        if [[ -f "$SCRIPT_DIR/$f" ]]; then
            cp "$SCRIPT_DIR/$f" "$DEPLOY_DIR/"
        fi
    done
fi
echo "   源代码已更新"

# ── 5. 安装 systemd 服务 ──
echo "[5/6] 安装 systemd 服务..."

# 获取 hermes 路径
HERMES_BIN="$HERMES_DIR/venv/bin"
if [[ ! -f "$HERMES_BIN/hermes" ]]; then
    # 尝试系统路径
    HERMES_BIN="$(dirname "$(which hermes 2>/dev/null || echo '/usr/local/bin/hermes')")"
fi

# agent 名称映射（中文名）
declare -A AGENT_NAMES=(
    [xiaoqing]="小青"
    [xiaobai]="小白"
    [xiaolan]="小蓝"
    [xiaohei]="小黑"
)
AGENT_NAME="${AGENT_NAMES[$AGENT]}"

# 构建 PATH
SAFE_PATH="$HERMES_BIN:/usr/local/bin:/usr/bin:/bin"

SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/mesh-${AGENT}.service" << EOF
[Unit]
Description=小希-Mesh 智能体 - ${AGENT_NAME}
After=network.target

[Service]
Type=simple
WorkingDirectory=${DEPLOY_DIR}
ExecStart=${HERMES_DIR}/venv/bin/python3 agent_runner.py --agent ${AGENT} --token ${TOKEN}
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=MESH_SERVER_HOST=${SERVER_HOST}
Environment=MESH_SERVER_PORT=${SERVER_PORT}
Environment=PATH=${SAFE_PATH}

[Install]
WantedBy=default.target
EOF

echo "   已创建: $SERVICE_DIR/mesh-${AGENT}.service"

# ── 6. 启动服务 ──
echo "[6/6] 启动服务..."
systemctl --user daemon-reload
systemctl --user enable "mesh-${AGENT}.service"
systemctl --user restart "mesh-${AGENT}.service"
sleep 2

# 验证
if systemctl --user is-active "mesh-${AGENT}.service" &>/dev/null; then
    echo ""
    echo "✅ 部署成功！"
    echo "   服务: mesh-${AGENT}.service"
    echo "   状态: $(systemctl --user is-active mesh-${AGENT}.service)"
    echo ""
    echo "常用命令:"
    echo "   查看日志: journalctl --user -u mesh-${AGENT} -f"
    echo "   重启服务: systemctl --user restart mesh-${AGENT}"
    echo "   停止服务: systemctl --user stop mesh-${AGENT}"
else
    echo ""
    echo "❌ 服务启动失败，查看日志:"
    journalctl --user -u "mesh-${AGENT}" -n 20 --no-pager
    exit 1
fi
