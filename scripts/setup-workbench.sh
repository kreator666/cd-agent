#!/usr/bin/env bash
# ------------------------------------------------------------------ #
# Workbench CLI 安装与验证脚本
# 用于安装阿里云 Workbench CLI 并验证配置
# ------------------------------------------------------------------ #
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ------------------------------------------------------------------ #
# 1. 检测操作系统和架构
# ------------------------------------------------------------------ #
detect_platform() {
    local os arch
    os="$(uname -s)"
    arch="$(uname -m)"

    case "$os" in
        Linux*)   PLATFORM="linux" ;;
        Darwin*)  PLATFORM="macos" ;;
        MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
        *)
            error "不支持的操作系统: $os"
            exit 1
            ;;
    esac

    case "$arch" in
        x86_64|amd64) ARCH="amd64" ;;
        arm64|aarch64) ARCH="arm64" ;;
        *)
            error "不支持的架构: $arch"
            exit 1
            ;;
    esac

    info "平台: $PLATFORM ($ARCH)"
}

# ------------------------------------------------------------------ #
# 2. 安装 Workbench CLI
# ------------------------------------------------------------------ #
install_workbench() {
    info "检查 workbench CLI 是否已安装..."

    if command -v workbench &>/dev/null; then
        local version
        version="$(workbench version 2>&1 | head -1 || echo 'unknown')"
        info "Workbench CLI 已安装: $version"
        return 0
    fi

    info "Workbench CLI 未安装，开始安装..."

    case "$PLATFORM" in
        linux|macos)
            info "下载安装脚本..."
            curl -fsSL https://workbench-cli.oss-cn-hangzhou.aliyuncs.com/install.sh | bash
            ;;
        windows)
            warn "Windows 请在 PowerShell 中执行："
            echo 'irm https://workbench-cli.oss-cn-hangzhou.aliyuncs.com/install.ps1 | iex'
            warn "安装完成后重新打开终端窗口以使 PATH 生效。"
            exit 0
            ;;
    esac

    # 刷新 PATH（兼容不同 shell）
    if [ -f "$HOME/.bashrc" ]; then
        # shellcheck disable=SC1091
        source "$HOME/.bashrc" 2>/dev/null || true
    fi
    if [ -f "$HOME/.zshrc" ]; then
        # shellcheck disable=SC1091
        source "$HOME/.zshrc" 2>/dev/null || true
    fi

    if command -v workbench &>/dev/null; then
        info "安装成功！"
        workbench version
    else
        error "安装后无法找到 workbench 命令。请检查 PATH 配置。"
        error "尝试使用绝对路径: /usr/local/bin/workbench version"
        exit 1
    fi
}

# ------------------------------------------------------------------ #
# 3. 配置凭证
# ------------------------------------------------------------------ #
check_config() {
    local config_file="$HOME/.workbench/config.json"

    info "检查凭证配置..."

    if [ ! -f "$config_file" ]; then
        warn "凭证配置文件不存在: $config_file"
        warn "请执行以下命令配置 AccessKey："
        echo ""
        echo "  workbench config"
        echo ""
        warn "配置指南: https://help.aliyun.com/zh/ecs/user-guide/install-and-configure-workbench-cli-credentials"
        return 1
    fi

    # 检查文件权限
    local perms
    perms="$(stat -c %a "$config_file" 2>/dev/null || stat -f %Lp "$config_file" 2>/dev/null || echo '000')"
    if [ "$perms" != "600" ]; then
        warn "配置文件权限不安全 ($perms)，建议设置为 600"
        chmod 600 "$config_file" 2>/dev/null || true
        info "已自动修复权限为 600"
    fi

    info "凭证配置文件存在: $config_file"

    # 尝试列出 Profile
    if command -v workbench &>/dev/null; then
        info "当前 Profile 列表："
        workbench config list 2>&1 || true
    fi

    return 0
}

# ------------------------------------------------------------------ #
# 4. 验证连通性
# ------------------------------------------------------------------ #
verify_connection() {
    local region="${1:-cn-hangzhou}"

    info "验证到 $region 的连通性..."

    if ! command -v workbench &>/dev/null; then
        error "workbench 命令不可用"
        return 1
    fi

    info "查询 $region 实例列表..."
    if workbench list ecs -r "$region" --limit 5; then
        info "✅ 连通性验证成功！"
        return 0
    else
        error "❌ 连通性验证失败。可能的原因："
        error "  1. AccessKey 配置有误"
        error "  2. RAM 用户缺少权限"
        error "  3. 网络无法访问 *.aliyuncs.com"
        error "  4. 地域 ID 不正确"
        return 1
    fi
}

# ------------------------------------------------------------------ #
# 5. 检查环境变量配置
# ------------------------------------------------------------------ #
check_env() {
    info "检查 .env 环境变量..."

    local env_file=".env"
    if [ ! -f "$env_file" ]; then
        warn ".env 文件不存在。建议复制 .env.example 并配置。"
        return 0
    fi

    # 检查 ECS 相关变量
    if grep -q "ECS_WORKBENCH_ENABLED=true" "$env_file" 2>/dev/null; then
        info "ECS_WORKBENCH_ENABLED=true ✅"
    else
        info "ECS_WORKBENCH_ENABLED=false (未启用，设置为 true 以启用 ECS 远程运维)"
    fi

    local region
    region="$(grep -E '^ECS_DEFAULT_REGION=' "$env_file" 2>/dev/null | cut -d'=' -f2 || echo 'cn-hangzhou')"
    info "ECS_DEFAULT_REGION=$region"
}

# ------------------------------------------------------------------ #
# 主流程
# ------------------------------------------------------------------ #
main() {
    echo "=========================================="
    echo "  阿里云 Workbench CLI 安装与验证"
    echo "=========================================="
    echo ""

    detect_platform

    echo ""
    info "步骤 1/4: 安装 Workbench CLI"
    install_workbench

    echo ""
    info "步骤 2/4: 检查凭证配置"
    check_config || true

    echo ""
    info "步骤 3/4: 检查环境变量"
    check_env

    echo ""
    info "步骤 4/4: 验证连通性"
    local region="${ECS_DEFAULT_REGION:-cn-hangzhou}"
    verify_connection "$region" || true

    echo ""
    echo "=========================================="
    info "设置完成！"
    echo ""
    echo "  如需配置凭证: workbench config"
    echo "  如需切换 Profile: workbench config switch --profile <name>"
    echo "  查询实例: workbench list ecs -r <region>"
    echo "  执行命令: workbench exec -i <instance-id> -c \"<command>\""
    echo "  交互连接: workbench connect -i <instance-id>"
    echo ""
    echo "  文档: https://help.aliyun.com/zh/ecs/user-guide/connect-to-an-instance-through-workbench-cli/"
    echo "=========================================="
}

main "$@"
