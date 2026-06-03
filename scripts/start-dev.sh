#!/bin/bash
# Comedy Agent —— 开发模式启动脚本（带热重载）
# 用法: bash scripts/start-dev.sh

set -e

# 定位项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# 加载 .env 环境变量
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# 优先使用虚拟环境的 uvicorn
if [ -f "$PROJECT_DIR/.venv/bin/uvicorn" ]; then
    UVICORN="$PROJECT_DIR/.venv/bin/uvicorn"
elif [ -f "$PROJECT_DIR/venv/bin/uvicorn" ]; then
    UVICORN="$PROJECT_DIR/venv/bin/uvicorn"
elif command -v uvicorn &>/dev/null; then
    UVICORN="uvicorn"
else
    echo "[ERR] 未找到 uvicorn，请先安装依赖: pip install -e \".[dev]\""
    exit 1
fi

echo "[INFO] 使用 uvicorn: $UVICORN"
echo "[INFO] 启动开发服务器（热重载已开启）..."
echo "[INFO] API 地址: http://0.0.0.0:8000"
echo "[INFO] 前端页面: http://0.0.0.0:8000/static/index.html"
echo "[INFO] 按 Ctrl+C 停止服务"
echo ""

exec "$UVICORN" comedy_agent.api.server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload
