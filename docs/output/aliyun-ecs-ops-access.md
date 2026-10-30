# 阿里云 ECS 运维连接方式

记录如何连接 `47.86.55.179` 进行运维。

## 连接方式概览

**首选 SSH 直连**（已配置免密部署密钥），Workbench CLI 作为备用（云助手通道，免 SSH 密钥）。

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

### 0. SSH 直连（首选）

```bash
ssh claw                              # 已配好别名（~/.ssh/config → claw_deploy 密钥）
ssh -i ~/.ssh/claw_deploy root@47.86.55.179   # 完整写法
```

- 密钥：`~/.ssh/claw_deploy`（ed25519 免密部署专用，公钥在服务器 `/root/.ssh/authorized_keys`）
- 注意：本机 `id_ed25519` 带密码短语，非交互场景不要用
- 文件传输用 `scp` / `rsync`，例如：`scp ./index.html claw:/var/www/frontend/`

### 1. 交互式登录（备用，人工操作）

```bash
workbench connect -r cn-hongkong -i i-j6cefwm4czuvg3uklqpk
```

连上后按 `Tab` 弹出命令面板；`/exit` 或 `Ctrl+D` 退出。

### 2. 远程执行单条命令（备用，脚本/Agent 运维）

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

### 发布流程（照做即可）

服务器上仓库路径：`/root/workspace/cd-agent`（分支 `v3_new`），nginx 站点目录：`/var/www/frontend`。

**标准发布（改完代码并 push 到 GitHub 后）：**

```bash
ssh claw 'cd /root/workspace/cd-agent && git pull origin v3_new && cp -r frontend/. /var/www/frontend/'
```

然后验证：

```bash
curl -sk -o /dev/null -w "%{http_code}\n" https://www.comedyclaw.cn/        # 期望 200
curl -sk -o /dev/null -w "%{http_code}\n" https://www.comedyclaw.cn/health    # 期望 200
```

**说明：**
- 前端静态文件：`cp -r frontend/. /var/www/frontend/` 即生效，无需重启 nginx
- 后端 Python 代码：uvicorn 以 `--reload` 运行，pull 后自动热重载，无需手动重启
- 改了 `requirements.txt` 或 uvicorn 挂掉时，才需要重启后端：

```bash
ssh claw 'ps aux | grep "uvicorn comedy_agent" | grep -v grep | awk "{print \$2}" | xargs -r kill; cd /root/workspace/cd-agent && nohup python3 -m uvicorn comedy_agent.api.server:app --host 0.0.0.0 --port 8000 --reload > /var/log/uvicorn.log 2>&1 &'
```

**只改单个前端文件的快速发布：**

```bash
scp ./frontend/xxx.html claw:/var/www/frontend/xxx.html
```

### 备用：Workbench 通道发布（云助手正常时可用）

本地：`tar --force-local -czf frontend.tar.gz -C frontend .` → `workbench upload -f` 到服务器 `/var/www/` → 解压覆盖。

## 注意事项

- **必须指定 `-r cn-hongkong`**：不带区域参数时默认区域查不到这台实例（会返回空列表）。
- 若 `list ecs` 返回空，先确认 AK 凭据仍有效（`workbench config list`），再排查区域。
- Workbench 通道**仅支持 Linux 实例**，Windows 实例不可用。
- 首次连接某台机器需要实例上的云助手 agent 在线（Running 状态一般即满足）。
- 安全组需放行 **80 和 443** 端口（80 用于证书续期验证，不可关）。
