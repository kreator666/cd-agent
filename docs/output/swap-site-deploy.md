# 交换市场副站（Swap）部署说明

物品/服务交换平台副站：复用主站后端（`/swap/*` 路由模块 + `swap_orders`/`swap_offers` 两张新表），独立前端站点，独立域名。

## 架构

```
swap.comedyclaw.cn (副站)         www.comedyclaw.cn (主站，不动)
├ nginx: /etc/nginx/conf.d/swap.conf
├ 静态根: /var/www/swap  ← 仓库 swap-frontend/ 的拷贝
├ /static/* → alias /var/www/frontend/（后端上传图片 URL 是 /static/swap_images/...）
└ 其余 → 反代 127.0.0.1:8000（与主站同一个 FastAPI 进程）
```

- 账号与主站完全共用（同一 `/auth`、同一 JWT、同一 SQLite）
- 后端 pull 后 uvicorn `--reload` 自动建表热重载；前端 scp 覆盖即生效

## 发布流程

```bash
# 1. 后端（服务器自动建表 + 热重载）
ssh claw 'cd /root/workspace/cd-agent && git pull origin v3_new'
# 2. 前端（Windows 本地无 rsync，用 scp 全量覆盖；删页面文件需手动 rm）
cd swap-frontend && scp -q *.html *.css *.js claw:/var/www/swap/
# 3. 验证
ssh claw 'curl -s -o /dev/null -w "%{http_code}" -H "Host: swap.comedyclaw.cn" http://127.0.0.1/index.html'   # 期望 200
curl -sk -o /dev/null -w "%{http_code}\n" https://www.comedyclaw.cn/                                          # 主站期望 200
```

## 域名 / HTTPS 状态

- 占位域名：`swap.comedyclaw.cn`。**需要配置 DNS**：A 记录 → `47.86.55.179`
- 当前仅监听 80 端口；DNS 生效后补 HTTPS：
  ```bash
  ssh claw '/root/.acme.sh/acme.sh --issue -d swap.comedyclaw.cn --webroot /var/www/frontend ...'  # 沿用主站 acme.sh 模式
  ```
  然后在 swap.conf 参照主站加 443 server + 80 跳转，证书放 `/etc/nginx/ssl/`
- 换正式独立域名时：改 swap.conf 的 `server_name`，重新签发证书即可

## nginx 配置要点（swap.conf）

- html 不缓存，css/js/图片缓存 7 天
- `/static/` alias 到主站静态目录（upload 接口把图存到仓库 `frontend/swap_images/`，同步主站时 `cp -r frontend/. /var/www/frontend/` 会带上）
- `client_max_body_size 50m`（图片上传限制在接口层另校 10MB）

## 运营操作

- 精选：用 admin 账号（`ADMIN_USER_ID`）登录副站，订单详情页点 ☆ 星标加精/取消
