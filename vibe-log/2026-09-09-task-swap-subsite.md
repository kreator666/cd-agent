# 任务执行记录

## 任务信息
- **阶段**: 新副站
- **任务编号**: swap-1.0
- **任务名称**: 物品/服务交换平台副站（Comedy Swap）设计与实现
- **执行日期**: 2026-09-09

## 任务说明
新增交换平台副站：maker 发单（如拿一场脱口秀换东西）→ taker 提交 offer（物品/服务，可配图、留联系方式）→ maker 挑选成交 → 其余自动落选；admin 可对订单加精，精选在首页突出展示。要求后端复用主站（独立模块、不影响主站功能）、前端独立站点、独立域名、主站导航留入口。

## 完成内容
**后端（复用主站架构，零改动现有表/路由）**
- `routers/swap.py`（prefix=/swap，10 接口）：发单/列表/详情/我的订单/我的意向/提交意向（一人一单去重更新）/成交（事务性：其余意向自动 rejected）/关闭/admin 精选/图片上传
- 新表 `swap_orders` / `swap_offers`（schema.py 追加，`create_all` 自动建表零迁移；`accept_swap_offer` 为事务性成交新增存储方法）
- 联系方式脱敏：成交前仅 maker 可见、成交后双方可见；详情接口带 `my_offer` 供 taker 表单回填
- server.py 仅加 import + include_router 两行

**前端（独立站点 `swap-frontend/`，设计语言与主站一致）**
- 5 页：index（精选区+列表+搜索+加载更多）、order（按 maker/taker/成交/admin 身份切换操作区）、create、me（我的单/我的意向）、login（复用主站 /auth，账号互通）
- 共享 `swap-common.css` + 精简 `common.js`；图片先传 `/swap/upload` 再提交
- 主站 `frontend/index.html` 顶栏加「交换市场」入口（唯一改动）

**部署（47.86.55.179）**
- 后端 pull 热重载，`/swap/orders` 200；`swap-frontend/` scp 至 `/var/www/swap/`
- 新增 `/etc/nginx/conf.d/swap.conf`（server_name swap.comedyclaw.cn 占位，80 端口；/static alias 主站目录、其余反代 127.0.0.1:8000），nginx -t 通过并 reload，主站 200 无回归
- 服务器本机以 swap Host 访问公网 IP 返回 200（配置正确）

## Commit 记录
- **Commit ID**: `3dce216`（功能）+ `1026ac9`（部署文档）
- **Commit Message**: `feat(swap): 新增物品/服务交换平台副站` / `docs(swap): 交换市场副站部署说明`
- **Branch**: `v3_new` → `origin/v3_new`

## 备注
- 测试：`tests/test_swap_api.py` 11 全过（含 my_offer 回填）；`test_speed_api` + `test_api_new_routers` 回归 14 全过
- 部署文档：`docs/output/swap-site-deploy.md`
- **待用户操作**：~~配置 DNS~~ ✅ 已完成；~~补 HTTPS~~ ✅ 已完成（2026-10-01：acme.sh ECC 证书签发并 install-cert，443 启用 + 80 跳转，验证 swap-https 200 / 301 / API 200 / 未登录写接口 401 / 主站 200）
- 前端接口未做真实浏览器联调（后端契约已逐字段核对：orders/total/page、my_offer、upload url），建议走一遍端到端

## 线上问题修复（同日）

- **症状**：主站账号在副站"登录不了"，提交订单被弹回登录页
- **根因**：`swap-frontend/login.html` 内联脚本重复声明 `const API_BASE`（common.js 已有）→ 经典脚本共享全局词法作用域 → 整个内联块 SyntaxError 不执行 → handleLogin 未定义、表单原生 GET 提交刷新、tab 无响应
- **排查路径**：curl 证明后端/证书/nginx 全链路正常 → 桌面浏览器复现 → headless Chrome dump-dom 发现 JS 未执行（浮动图标 0 个，对照主站 18 个）→ console 日志定位 SyntaxError
- **修复**：commit `78de8d0` 移除重复声明，scp 上线；桌面浏览器端到端验证：登录→index 跳转→create 发单→order 详情全链路通过
- **教训**：静态截图自检发现不了脚本整体不执行类 bug，上线验证必须看 console / 执行态 DOM；其余 4 页无重复声明（已全量 grep 确认）
- 测试数据已清理（swap_e2e_test 账号 + 2 个测试订单 + jstest.html）

## 线上问题修复 2：上传图片 404（同日）

- **症状**：发布交换上传图片后，图片 URL `/static/swap_images/xxx.png` 404
- **根因**（两层）：
  1. 上传保存到仓库 `frontend/swap_images/`，但 nginx `/static/` alias 指向部署目录 `/var/www/frontend`，运行时上传不在部署目录
  2. swap.conf 把资源缓存正则放在顶层，`.png/.jpg` 请求被正则抢先匹配（root 是副站目录），`/static/` alias 根本没生效（主站 frontend.conf 用的是嵌套写法所以没事）
- **修复**：commit `07f6b28` —— 新增 `STATIC_DEPLOY_DIR` 配置（服务器 .env 配 `/var/www/frontend`），上传时镜像一份到部署目录；swap.conf `/static/` 改嵌套 location；用户已上传的图片手动补拷
- **验证**：服务器直传后端 → 两目录都有文件 → 公网 URL 200；测试数据已清理
- **遗留同构问题**：~~主站 `/me/avatar`、`/me/tipping-config` 的上传同样存仓库目录，运行时新头像在主站也会 404（历史遗留，本次未动，修法相同）~~ ✅ 已修复（commit `2abdd8d`）：抽取共享助手 `api/static_mirror.py`，头像/收款码/swap 三处上传统一接入；线上 E2E 验证两个公网 URL 均 200，测试数据已清理
- **附带说明**：用户浏览器报 `contentscript.js MaxListenersExceededWarning / ObjectMultiplex orphaned data` 是浏览器扩展（MetaMask 类钱包插件）的告警，与本站代码无关

## 线上问题修复 3：首页卡片点击进不了详情（commit `e22fb7d`）

- **根因**：卡片模板 `onclick="goOrder(${order_id})"` 未加引号，uuid 被浏览器当成未定义变量 → ReferenceError → 点击无反应（列表卡片、精选卡片两处同病）
- **修复**：改为 `goOrder('${order_id}')`；浏览器端到端验证：首页点卡片 → order.html?id=xxx 详情页正常渲染；种子数据已清理

## 线上问题修复 4：「选这个成交」无反应（commit `adf1acf`）

- **根因 1（直接原因）**：`onclick="acceptOffer(${offer_id})"` 未加引号（同首页卡片病），点击抛 ReferenceError 无反应；me.html 两处 `goOrder` 同病一并修复
- **根因 2（验证中连带发现）**：前端状态映射写的 `matched`，后端实际是 `deal` → 状态标签显示原始 "deal"、成交 taker 进不了成交卡分支（三个页面统一改 `deal`）；`isMaker` 判定含 `offers!==null`，成交 taker 也带 offers 被误判成 maker
- **验证**：API 造数 → 浏览器 maker 登录点成交 → 确认弹窗 → deal 生效、offer accepted、contact 明文 → taker 登录看到「🎉 恭喜成交」成交卡（含成交内容与联系方式）→ 状态标签显示「已成交」；测试数据已清理
