# 任务执行记录

## 任务信息
- **阶段**: 前端与后端功能扩展
- **任务编号**: N/A
- **任务名称**: 增加 USDT 以太坊地址打赏
- **执行日期**: 2026-08-21

## 任务说明
在现有微信二维码打赏基础上，增加 USDT（ERC-20 / 以太坊地址）打赏方式：
1. 作者可在「我的」页面填写以太坊收款地址；
2. 段子广场详情页展示「USDT 打赏」标签，根据地址生成二维码并显示地址；
3. 付款方可用钱包扫码或复制地址转账。

## 完成内容
- 数据层
  - `UserProfile` 表新增 `usdt_address` 字段（nullable，长度 64）
  - `UserProfileData` 模型新增 `usdt_address`
  - `SQLMemoryStore` 与 `UnifiedMemory` 的 `get_user` / `update_user_profile` 透传该字段
  - 启动时 `_sync_schema()` 会自动为旧库添加该列
- 后端 API
  - `src/comedy_agent/api/routers/wallet.py`
    - `/me/tipping-config` 响应新增 `usdt_address`
    - `POST /me/tipping-config` 接受并保存 `usdt_address`，校验 `0x` 开头的 42 位十六进制地址
    - 新增 `GET /tipping/usdt-qr/{user_id}`，使用 `qrcode` 库生成地址二维码 PNG 图片流
- 广场接口
  - `src/comedy_agent/api/routers/eval.py`
    - `SquareJokeItem` / `SquareJokeDetail` 新增 `author_usdt_address`
    - 广场列表/详情序列化时从作者资料读取并返回
- 前端
  - `frontend/me.html`
    - 「微信打赏设置」标题改为「打赏设置」
    - 新增 USDT 收款地址输入框与前端格式校验
  - `frontend/eval-square.html`
    - 打赏区增加「微信打赏」/「USDT 打赏」标签切换
    - USDT 标签页展示二维码图片、明文地址与复制按钮
    - 列表卡片只要有微信二维码或 USDT 地址即显示 💰 打赏按钮
- 验证
  - `python -m py_compile` 校验所有改动 Python 文件语法通过
  - `node --check` 校验两个前端页面内联 JS 语法通过
  - `pytest tests/test_tipping.py` 全部通过（5 passed）
  - `pytest tests/test_eval_square_api.py` 前 7 个用例通过，后续用例在本地运行较慢（可能与本次改动无关）

## Commit 记录
- **Commit ID**: `eb96bfd85d30939b8ee9c0f1870e9431a9c18c15`
- **Commit Message**: `feat(tipping): 增加 USDT 以太坊地址打赏`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- USDT 打赏仅展示收款地址与二维码，无法自动统计链上金额（与微信打赏同理）。
- 当前仅支持 ERC-20 以太坊地址，TRC-20 等其他链可后续扩展。
