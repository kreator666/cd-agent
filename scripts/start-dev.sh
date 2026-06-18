#!/bin/bash
# Comedy Agent —— 开发模式启动脚本（带热重载与自动重启）
# 用法:
#   bash scripts/start-dev.sh         # 启动/重启开发服务器
#   bash scripts/start-dev.sh stop    # 停止正在运行的开发服务器
#   bash scripts/start-dev.sh restart # 等同于默认行为：停止旧服务并重新启动

set -e

# 定位项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# PID 文件路径
PID_FILE="$PROJECT_DIR/data/.dev-server.pid"
mkdir -p "$PROJECT_DIR/data"

# 加载 .env 环境变量
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# 确保 Python 能找到 src 下的模块（editable 未安装时的兜底）
export PYTHONPATH="${PROJECT_DIR}/src:${PYTHONPATH:-}"

# Python 解释器（兼容 Windows/Git Bash 中 python3/python 别名不一致的情况）
# 优先选择已经能导入 comedy_agent 的解释器
PYTHON_BIN=""
for py in python3 python py; do
    if command -v "$py" &>/dev/null && "$py" -c "import comedy_agent" 2>/dev/null; then
        PYTHON_BIN="$py"
        break
    fi
done
# 若没有能导入模块的解释器，则 fallback 到第一个可用的
if [ -z "$PYTHON_BIN" ]; then
    for py in python3 python py; do
        if command -v "$py" &>/dev/null; then
            PYTHON_BIN="$py"
            break
        fi
    done
fi
if [ -z "$PYTHON_BIN" ]; then
    echo "[ERR] 未找到 Python 解释器"
    exit 1
fi

# 优先使用虚拟环境的 uvicorn
if [ -f "$PROJECT_DIR/.venv/bin/uvicorn" ]; then
    UVICORN="$PROJECT_DIR/.venv/bin/uvicorn"
elif [ -f "$PROJECT_DIR/venv/bin/uvicorn" ]; then
    UVICORN="$PROJECT_DIR/venv/bin/uvicorn"
elif [ -f "$PROJECT_DIR/.venv/Scripts/uvicorn.exe" ]; then
    UVICORN="$PROJECT_DIR/.venv/Scripts/uvicorn.exe"
elif [ -f "$PROJECT_DIR/venv/Scripts/uvicorn.exe" ]; then
    UVICORN="$PROJECT_DIR/venv/Scripts/uvicorn.exe"
elif "$PYTHON_BIN" -m uvicorn --version &>/dev/null; then
    UVICORN="$PYTHON_BIN -m uvicorn"
elif command -v uvicorn &>/dev/null; then
    UVICORN="uvicorn"
else
    echo "[ERR] 未找到 uvicorn，请先安装依赖: pip install -e \".[dev]\""
    exit 1
fi

# 检查 comedy_agent 模块是否可导入
if ! "$PYTHON_BIN" -c "import comedy_agent" 2>/dev/null; then
    echo "[WARN] comedy_agent 模块未找到，尝试 editable 安装..."
    "$PYTHON_BIN" -m pip install -e "$PROJECT_DIR" 2>/dev/null || true
fi

# --------------------------------------------------------------------------- #
# 服务启停工具函数
# --------------------------------------------------------------------------- #
_get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE" 2>/dev/null || true
    fi
}

_is_running() {
    local pid="$1"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

_stop_server() {
    local old_pid
    old_pid=$(_get_pid)
    if [ -n "$old_pid" ] && _is_running "$old_pid"; then
        echo "[INFO] 检测到运行中的开发服务器 (PID: $old_pid)，正在停止..."
        kill "$old_pid" 2>/dev/null || true
        local i
        for i in $(seq 1 30); do
            if ! _is_running "$old_pid"; then
                echo "[INFO] 旧服务已停止。"
                break
            fi
            sleep 1
        done
        if _is_running "$old_pid"; then
            echo "[WARN] 旧服务未能在 30 秒内停止，强制终止..."
            kill -9 "$old_pid" 2>/dev/null || true
        fi
    elif [ -n "$old_pid" ]; then
        echo "[INFO] 未发现运行中的开发服务器，清理残留 PID 文件。"
    fi
    rm -f "$PID_FILE"
}

_start_server() {
    echo "[INFO] 使用 uvicorn: $UVICORN"
    echo "[INFO] 启动开发服务器（热重载已开启）..."
    echo "[INFO] API 地址: http://0.0.0.0:8000"
    echo "[INFO] 前端页面: http://0.0.0.0:8000/static/index.html"
    echo "[INFO] 按 Ctrl+C 停止服务"
    echo ""

    # exec 会用 uvicorn 替换当前 shell，因此当前 shell 的 PID 就是服务 PID
    echo $$ > "$PID_FILE"
    # shellcheck disable=SC2086
    exec $UVICORN comedy_agent.api.server:app \
        --host 0.0.0.0 \
        --port 8000 \
        --reload
}

# --------------------------------------------------------------------------- #
# 命令分发
# --------------------------------------------------------------------------- #
COMMAND="${1:-start}"

case "$COMMAND" in
    stop)
        _stop_server
        echo "[INFO] 开发服务器已停止。"
        ;;
    start|restart|""|*)
        if [ "$COMMAND" != "start" ] && [ "$COMMAND" != "restart" ] && [ -n "$COMMAND" ]; then
            echo "[WARN] 未知命令 '$COMMAND'，默认按 start 处理。"
        fi
        _stop_server
        _start_server
        ;;
esac
