#!/bin/bash
set -e

# ============================================================
# Comedy Agent —— All-in-One 裸机安装脚本
# 适用系统：Ubuntu 22.04/24.04 LTS / Debian 12
# 使用方法：bash deploy/install-native.sh
# ============================================================

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
PYTHON_VERSION="3.11"
VENV_DIR="$PROJECT_DIR/.venv"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERR]${NC}  $1"; }

# 检测 Linux 发行版
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    else
        echo "unknown"
    fi
}

DISTRO=$(detect_distro)
log_info "检测到操作系统: $DISTRO"

if [ "$DISTRO" != "ubuntu" ] && [ "$DISTRO" != "debian" ]; then
    log_warn "本脚本主要适配 Ubuntu/Debian，其他系统可能需要手动调整"
fi

# -------------- 1. 系统更新与基础依赖 --------------
log_info "更新系统并安装基础依赖..."
apt-get update -qq
apt-get install -y -qq \
    build-essential \
    curl \
    wget \
    git \
    software-properties-common \
    libmagic1 \
    redis-server \
    python3 \
    python3-dev \
    python3-venv \
    python3-pip \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev

log_ok "系统依赖安装完成"

# -------------- 2. 确保 Python 3.11+ --------------
log_info "检查 Python 版本..."
PYTHON_CMD=""

for cmd in python3.12 python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
        ver=$($cmd --version 2>&1 | awk '{print $2}')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON_CMD="$cmd"
            log_ok "使用 Python $ver ($PYTHON_CMD)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    log_info "Python 3.11+ 未找到，正在安装 Python 3.11..."
    add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
    apt-get update -qq
    apt-get install -y -qq python3.11 python3.11-dev python3.11-venv python3.11-distutils
    PYTHON_CMD="python3.11"
    log_ok "Python 3.11 安装完成"
fi

# -------------- 3. 配置 Redis --------------
log_info "配置 Redis..."
systemctl enable redis-server
systemctl restart redis-server

# 检查 Redis 是否运行
if redis-cli ping | grep -q PONG; then
    log_ok "Redis 运行正常"
else
    log_error "Redis 启动失败"
    exit 1
fi

# -------------- 4. 配置环境变量 --------------
log_info "检查环境变量配置..."

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
        log_warn ".env 文件不存在，已从 .env.example 复制，请编辑后重新运行本脚本"
        log_warn "编辑命令: nano $ENV_FILE"
        log_warn "至少需要配置一个 API Key（如 OPENAI_API_KEY）才能正常使用"
        exit 1
    else
        log_error ".env 文件和 .env.example 都不存在！"
        exit 1
    fi
fi

# 确保 REDIS_URL 指向本地
if grep -q "^REDIS_URL=" "$ENV_FILE"; then
    sed -i 's|^REDIS_URL=.*|REDIS_URL=redis://localhost:6379/0|' "$ENV_FILE"
else
    echo "REDIS_URL=redis://localhost:6379/0" >> "$ENV_FILE"
fi
log_ok "Redis URL 已配置为本地"

# -------------- 5. 创建 Python 虚拟环境 --------------
log_info "创建 Python 虚拟环境..."
if [ -d "$VENV_DIR" ]; then
    log_warn "虚拟环境已存在，将复用"
else
    $PYTHON_CMD -m venv "$VENV_DIR"
    log_ok "虚拟环境创建完成"
fi

source "$VENV_DIR/bin/activate"
pip install -q --upgrade pip

# -------------- 6. 安装项目依赖 --------------
log_info "安装项目 Python 依赖（可能需要几分钟）..."
cd "$PROJECT_DIR"
pip install -q -e ".[dev]"

# 可选：安装 Ollama 支持
if command -v ollama &>/dev/null; then
    log_ok "检测到 Ollama，安装 langchain-ollama..."
    pip install -q langchain-ollama || log_warn "langchain-ollama 安装失败，可稍后手动安装"
fi

log_ok "Python 依赖安装完成"

# -------------- 7. 创建数据目录 --------------
log_info "创建数据目录..."
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/chroma_data" "$PROJECT_DIR/skills"

# -------------- 8. 配置 systemd 服务 --------------
log_info "配置 systemd 服务..."

SYSTEMD_SERVICE="/etc/systemd/system/comedy-agent.service"
cat > "$SYSTEMD_SERVICE" <<EOF
[Unit]
Description=Comedy Agent API Service
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_DIR/bin/uvicorn comedy_agent.api.server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable comedy-agent
systemctl restart comedy-agent

# -------------- 9. 健康检查 --------------
log_info "等待服务启动（约 10 秒）..."
sleep 10

HEALTH_URL="http://localhost:8000/health"
for i in {1..10}; do
    if curl -fsS "$HEALTH_URL" &>/dev/null; then
        log_ok "API 服务健康检查通过！"
        break
    fi
    if [ "$i" -eq 10 ]; then
        log_error "API 服务启动超时，请检查日志: journalctl -u comedy-agent -f"
        exit 1
    fi
    log_info "健康检查第 $i/10 次重试..."
    sleep 5
done

# -------------- 10. 完成提示 --------------
IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "<服务器IP>")
[ -z "$IP_ADDR" ] && IP_ADDR="<服务器IP>"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            🎭 Comedy Agent 裸机部署完成！                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
log_ok  "API 地址:    http://$IP_ADDR:8000"
log_ok  "前端页面:    http://$IP_ADDR:8000/static/index.html"
log_ok  "健康检查:    http://$IP_ADDR:8000/health"
log_info "API 文档:    http://$IP_ADDR:8000/docs"
echo ""
log_info "服务管理命令:"
echo "  查看日志:   journalctl -u comedy-agent -f"
echo "  重启服务:   systemctl restart comedy-agent"
echo "  停止服务:   systemctl stop comedy-agent"
echo "  查看状态:   systemctl status comedy-agent"
echo ""
log_info "Redis 管理:"
echo "  状态检查:   redis-cli ping"
echo "  监控:       redis-cli monitor"
echo ""
log_warn "如需配置 HTTPS / 域名 / Nginx，请参考 deploy/DEPLOY.md"
