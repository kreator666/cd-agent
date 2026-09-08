# 阿里云 ECS 运维连接方式

记录如何通过 Workbench CLI 连接 `47.86.55.179` 进行运维。

## 连接方式概览

该服务器**不走 SSH 密钥直连**（服务器只认密钥，本机公钥未授权）。之前是通过**阿里云 Workbench CLI**（云助手通道，免 SSH 密钥/免公网 IP 要求）连接的。

## 环境信息

| 项目 | 值 |
|------|-----|
| 工具 | Workbench CLI（已安装，`~/.local/bin/workbench`，v1.0.1） |
| 凭据配置 | `~/.workbench/config.json`（AK 模式，profile: `default`） |
| 目标公网 IP | `47.86.55.179` |
| 实例 ID | `i-j6cefwm4czuvg3uklqpk` |
| 实例名 | `launch-advisor-20260603` |
| 区域 | `cn-hongkong`（中国香港） |
| 实例规格 | `ecs.e-c1m2.large`，Linux（Alibaba Cloud Linux） |

## 常用命令

### 1. 交互式登录（人工操作）

```bash
workbench connect -r cn-hongkong -i i-j6cefwm4czuvg3uklqpk
```

连上后按 `Tab` 弹出命令面板；`/exit` 或 `Ctrl+D` 退出。

### 2. 远程执行单条命令（脚本/Agent 运维）

```bash
workbench exec -r cn-hongkong -i i-j6cefwm4czuvg3uklqpk -c "<命令>" --output json
```

示例：

```bash
workbench exec -r cn-hongkong -i i-j6cefwm4czuvg3uklqpk -c "df -h && free -h" --output json
```

### 3. 文件传输

```bash
# 上传
workbench upload ./app.jar /opt/app/ -r cn-hongkong -i i-j6cefwm4czuvg3uklqpk

# 下载
workbench download /var/log/app.log ./ -r cn-hongkong -i i-j6cefwm4czuvg3uklqpk
```

### 4. 实例与会话管理

```bash
workbench list ecs -r cn-hongkong --output json   # 查实例列表
workbench session list                            # 活跃会话
workbench session close --all                     # 关闭所有会话
workbench daemon status                           # 后台守护进程状态
```

## 网站部署现状（2026-09-08 配置）

| 项目 | 值 |
|------|-----|
| 站点根目录 | `/var/www/frontend`（本仓库 `frontend/` 目录的拷贝） |
| nginx 配置 | `/etc/nginx/conf.d/frontend.conf`（80 强制跳转 443） |
| 域名 | `comedyclaw.cn` + `www.comedyclaw.cn`（均已解析到本机） |
| HTTPS 证书 | Let's Encrypt ECC 证书，`/etc/nginx/ssl/comedyclaw.crt` + `.key` |
| 证书管理 | acme.sh（`/root/.acme.sh`），cron 自动续期（约 60 天一次），reload 自动执行 |
| 后端 API | uvicorn `comedy_agent.api.server:app`，监听 **127.0.0.1:8000**（nginx 反代，支持 SSE 流式） |
| 前端资源 | 前端代码内链接硬编码为 `/static/xxx`，nginx 用 `alias` 映射到 `/var/www/frontend/` |

### nginx 路由规则（同一域名下前后端共存）

1. `/static/*` → alias 到站点根目录（兼容前端硬编码的 `/static/` 前缀）
2. 根路径下存在的文件（`/xxx.html`、`/common.css`、`/images/*` 等）→ 直接返回静态文件
3. 其余全部 → 反代到后端 `127.0.0.1:8000`（API 无 `/api` 前缀，`/health`、`/auth/*`、`/me/*`、`/eval/*` 等 122 个路由）
4. html 不缓存，css/js/图片缓存 7 天；`client_max_body_size 50m`（文件上传）

### 更新部署

本地：`tar --force-local -czf frontend.tar.gz -C frontend .` → `workbench upload` 到服务器 `/var/www/` → 解压覆盖。改前端代码后重启后端才生效（uvicorn 以 `--reload` 运行，改 Python 代码自动重载）。

## 注意事项

- **必须指定 `-r cn-hongkong`**：不带区域参数时默认区域查不到这台实例（会返回空列表）。
- 若 `list ecs` 返回空，先确认 AK 凭据仍有效（`workbench config list`），再排查区域。
- Workbench 通道**仅支持 Linux 实例**，Windows 实例不可用。
- 首次连接某台机器需要实例上的云助手 agent 在线（Running 状态一般即满足）。
- 安全组需放行 **80 和 443** 端口（80 用于证书续期验证，不可关）。
