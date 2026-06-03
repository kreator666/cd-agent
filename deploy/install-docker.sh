#!/bin/bash
set -e

# ============================================================
# Comedy Agent —— All-in-One Docker Compose 安装脚本
# 适用系统：Ubuntu 22.04/24.04 LTS / Debian 12 / CentOS 8+
# 使用方法：bash deploy/install-docker.sh
# ============================================================

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
ENV_FILE="$PROJECT_DIR/.env"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERR]${NC}  $1"; }

# 检查命令是否存在
check_cmd() {
    command -v "$1" &>/dev/null
}

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

# -------------- 1. 安装 Docker --------------
install_docker() {
    log_info "正在安装 Docker..."
    if [ "$DISTRO" = "ubuntu" ] || [ "$DISTRO" = "debian" ]; then
        apt-get update -qq
        apt-get install -y -qq ca-certificates curl gnupg lsb-release
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/$DISTRO/gpg -o /etc/apt/keyrings/docker.asc
        chmod a+r /etc/apt/keyrings/docker.asc
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$DISTRO $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
        apt-get update -qq
        apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    elif [ "$DISTRO" = "centos" ] || [ "$DISTRO" = "rhel" ] || [ "$DISTRO" = "fedora" ] || [ "$DISTRO" = "almalinux" ] || [ "$DISTRO" = "rocky" ]; then
        yum install -y -q yum-utils
        yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        yum install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        systemctl enable --now docker
    else
        log_error "不支持的操作系统: $DISTRO，请手动安装 Docker"
        exit 1
    fi
    log_ok "Docker 安装完成"
}

# 检查并安装 Docker
if check_cmd docker; then
    log_ok "Docker 已安装: $(docker --version)"
else
    install_docker
fi

# 检查 Docker Compose (Plugin 或 standalone)
if docker compose version &>/dev/null || check_cmd docker-compose; then
    log_ok "Docker Compose 已可用"
else
    log_warn "Docker Compose Plugin 未找到，尝试安装..."
    install_docker
fi

# 将当前用户加入 docker 组（避免 sudo）
if [ -n "${SUDO_USER:-}" ]; then
    usermod -aG docker "$SUDO_USER" 2>/dev/null || true
    log_info "已将 $SUDO_USER 加入 docker 组，重新登录后无需 sudo"
fi

# -------------- 2. 检查环境变量 --------------
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

# 检查是否配置了至少一个 API Key
API_KEYS=$(grep -E '^(OPENAI_API_KEY|ANTHROPIC_API_KEY|DASHSCOPE_API_KEY|MOONSHOT_API_KEY)=' "$ENV_FILE" | grep -v '=sk-\.\.\.' | grep -v '=$' || true)
if [ -z "$API_KEYS" ]; then
    log_warn "未检测到有效的 API Key，请编辑 $ENV_FILE 配置至少一个 Key"
    log_warn "如果计划使用 Ollama 本地模型，可以忽略此警告"
fi

# -------------- 3. 创建数据目录 --------------
log_info "创建数据目录..."
mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/chroma_data" "$PROJECT_DIR/skills"

# -------------- 4. 构建并启动服务 --------------
log_info "构建并启动 Comedy Agent 服务..."
cd "$PROJECT_DIR"

# 使用 docker compose plugin 或 docker-compose
docker_compose_cmd="docker compose"
if ! docker compose version &>/dev/null; then
    docker_compose_cmd="docker-compose"
fi

# 拉取最新镜像并构建
$docker_compose_cmd -f "$COMPOSE_FILE" pull
$docker_compose_cmd -f "$COMPOSE_FILE" up -d --build

# -------------- 5. 健康检查 --------------
log_info "等待服务启动（约 15 秒）..."
sleep 15

HEALTH_URL="http://localhost:8000/health"
for i in {1..10}; do
    if curl -fsS "$HEALTH_URL" &>/dev/null; then
        log_ok "API 服务健康检查通过！"
        break
    fi
    if [ "$i" -eq 10 ]; then
        log_error "API 服务启动超时，请检查日志: $docker_compose_cmd -f $COMPOSE_FILE logs -f api"
        exit 1
    fi
    log_info "健康检查第 $i/10 次重试..."
    sleep 5
done

# -------------- 6. 完成提示 --------------
IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "$(hostname -I | awk '{print $1}')")
[ -z "$IP_ADDR" ] && IP_ADDR="<服务器IP>"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            🎭 Comedy Agent 部署完成！                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
log_ok  "API 地址:    http://$IP_ADDR:8000"
log_ok  "前端页面:    http://$IP_ADDR:8000/static/index.html"
log_ok  "健康检查:    http://$IP_ADDR:8000/health"
log_info "API 文档:    http://$IP_ADDR:8000/docs"
echo ""
log_info "常用命令:"
echo "  查看日志:   $docker_compose_cmd -f $COMPOSE_FILE logs -f api"
echo "  重启服务:   $docker_compose_cmd -f $COMPOSE_FILE restart api"
echo "  停止服务:   $docker_compose_cmd -f $COMPOSE_FILE down"
echo "  更新代码:   git pull && $docker_compose_cmd -f $COMPOSE_FILE up -d --build"
echo ""
log_warn "如需配置 HTTPS / 域名 / Nginx，请参考 deploy/DEPLOY.md"
