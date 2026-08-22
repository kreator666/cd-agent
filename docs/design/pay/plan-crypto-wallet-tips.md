# 加密货币打赏（用户钱包绑定 + 链上校验）开发方案

> 需求来源：`docs/design/pay/打赏.md`

## 1. 目标

把现有的打赏能力从「平台统一收款」升级为「读者用个人钱包付款、作者用个人钱包收款、平台通过 Anyway 订单 + Base 链上交易做凭证校验」的模式。

- 用户在「我的」页面绑定一个钱包地址（收款地址 & 付款地址）。
- 绑定地址时必须用 **EIP-712 签名** 证明地址所有权，签名提示内容要明确。
- 打赏时：读者的钱包作为付款地址；平台生成 Anyway 付款链接并把 `result_id`、作者地址、读者地址写入 `merchantMetadata`。
- 到账后：通过 Anyway Merchant API / Webhook 拿到订单，再用链上交易 hash 到 Base 网络校验转账金额与收款地址，匹配后入账。
- 统计：每个用户可以看到「我打赏了多少钱」和「我收到了多少钱」，以及关联的订单/交易明细。

## 2. 关键假设与待确认点

| 问题 | 当前处理方案 |
|------|------------|
| Anyway 订单是否直接返回 Base 链上交易 hash？ | 先按「Webhook / 订单详情里有 `transactionHash` 或 `txHash`」设计；若 Anyway 不返回，则提供读者手动回填交易 hash 的入口。 |
| 打赏币种 | 先支持 Base 链 USDC / ETH；后续可扩展。 |
| 网络 RPC | 需配置 Base 主网 RPC（Alchemy/Infura/公开节点），用于链上校验。 |
| 手续费 | 暂由平台设定一个固定比例；后续可配置。 |

## 3. 数据模型变更

### 3.1 `user_profiles` 表新增字段

```python
wallet_address: str | None   # 0x... Base/Ethereum 地址
wallet_signature: str | None # EIP-712 签名 hex
wallet_signed_at: datetime | None
wallet_chain: str = "base"     # 默认 base，可扩展
```

### 3.2 新增 `crypto_tip_orders` 表

记录每一次加密货币打赏订单。

| 字段 | 说明 |
|------|------|
| `order_id` | 本地主键 |
| `anyway_order_id` | Anyway 订单 ID |
| `merchant_reference` | 关联用 merchant reference |
| `result_id` | 被打赏的广场段子 ID |
| `payer_user_id` | 打赏读者用户 ID |
| `payer_wallet` | 读者付款地址 |
| `author_user_id` | 被打赏作者用户 ID |
| `author_wallet` | 作者收款地址 |
| `amount_cents` | 金额（美分 / 对应币种最小单位） |
| `currency` | 币种，如 `USDC`、`ETH` |
| `tx_hash` | Base 链上交易 hash |
| `status` | `pending` / `paid` / `failed` / `refunded` |
| `verified_at` | 链上校验通过时间 |
| `metadata_json` | Anyway 订单原始数据、链上 receipt 等 |
| `created_at` / `paid_at` | 时间戳 |

### 3.3 新增 `user_crypto_stats` 视图 / 聚合函数

基于 `crypto_tip_orders` 实时汇总：

- `total_tipped_cents`：我作为 payer 的成功打赏总额。
- `total_received_cents`：我作为 author 的成功收款总额。
- 最近订单列表。

## 4. 服务端接口设计

### 4.1 钱包绑定

```
GET  /me/wallet-address        # 获取当前绑定地址与签名状态
POST /me/wallet-address        # 提交地址 + EIP-712 签名进行绑定
```

请求体示例：

```json
{
  "address": "0x...",
  "signature": "0x...",
  "chain": "base"
}
```

服务端验证：
1. 地址格式校验（`0x` + 40 位十六进制）。
2. 用 EIP-712 恢复签名者地址，必须等于提交地址。
3. 签名消息模板：

```text
我确认将地址 {address} 绑定为 Comedy Agent 的加密货币打赏地址，用于接收和支付打赏。
```

### 4.2 创建加密货币打赏意图

```
POST /tips/crypto/intent
```

请求体：

```json
{
  "result_id": "res_xxx",
  "amount_cents": 500,
  "currency": "USDC"
}
```

校验：
1. 当前登录用户必须已绑定钱包（作为 payer）。
2. 不能给自己打赏。
3. 被打赏作者必须已绑定钱包（作为收款地址）。
4. 金额在限制范围内。

响应：

```json
{
  "order_id": "cto_xxx",
  "payment_url": "https://pay.anyway.sh/pay/PL_xxx?merchant_reference=cto_xxx&payer_wallet=0x...&author_wallet=0x...",
  "payer_wallet": "0x...",
  "author_wallet": "0x...",
  "amount_cents": 500,
  "currency": "USDC"
}
```

### 4.3 链上校验与入账

#### 方案 A：自动（Webhook + 轮询）

- 监听 `order.paid` Webhook。
- 收到后根据 `merchant_reference` 找到本地 `crypto_tip_orders`。
- 从 Anyway 订单详情读取 `transactionHash` / `txHash`（或从 `merchantMetadata` 扩展字段）。
- 调用 Base RPC 获取 receipt，校验：
  - `to` 是作者钱包地址；
  - 转账金额 >= 订单金额；
  - 交易状态成功且确认数足够。
- 更新 `crypto_tip_orders` 为 `paid`，并写入 `verified_at`。

#### 方案 B：手动回填（兜底）

```
POST /tips/crypto/confirm
```

请求体：

```json
{
  "order_id": "cto_xxx",
  "tx_hash": "0x..."
}
```

服务端做同样的链上校验后入账。

### 4.4 统计接口

```
GET /tips/crypto/stats          # 当前用户
GET /tips/crypto/orders         # 当前用户的打赏/收款订单列表
```

响应示例：

```json
{
  "total_tipped_cents": 1500,
  "total_received_cents": 800,
  "currency": "USDC",
  "bound_wallet": "0x..."
}
```

## 5. 前端 UI 改造

### 5.1 「我的」页面（`frontend/me.html`）

新增「加密货币钱包」卡片：

- 显示当前绑定地址（只读）。
- 未绑定时：输入框 +「生成签名消息」按钮。
- 签名消息内容展示在页面上，用户用钱包（MetaMask / Rabby / OKX Wallet）签名后回填签名。
- 「验证并绑定」按钮提交到 `/me/wallet-address`。
- 已绑定时：显示地址和绑定时间，提供「更换地址」按钮（重新走签名流程）。

在「我的打赏收益」卡片下方新增「加密货币打赏统计」卡片：

- 我打赏了：$x.xx
- 我收到：$x.xx
- 最近订单列表（时间、对方地址、金额、状态、交易 hash 链接到 BaseScan）。

### 5.2 广场详情页（`frontend/eval-square.html`）

打赏区新增「Crypto 打赏」标签页（与微信 / USDT / Anyway 并列或合并）：

- 输入金额（USD）。
- 调用 `/tips/crypto/intent` 生成支付链接。
- 显示：
  - 支付链接（点击跳转 Anyway 收银台）。
  - 作者的收款地址。
  - 提示：「请使用已绑定的钱包 {payer_wallet} 完成支付」。
- 若 30 秒后未自动确认，显示「我已支付，提交交易 hash」输入框，调用 `/tips/crypto/confirm`。

### 5.3 管理后台（`frontend/admin-console.html`）

新增「Crypto 打赏订单」标签页：

- 列出所有 `crypto_tip_orders`。
- 支持按状态筛选。
- 展示 payer、author、金额、tx_hash、校验结果。
- 提供「手动触发链上校验」按钮（用于 Webhook 未送达时重试）。

## 6. 流程时序

```text
读者                        后端                       Anyway              Base 链
 |                           |                           |                   |
 |-- 绑定钱包（签名）-------->|-- 校验 EIP-712 ---------->|                   |
 |<-------------------------|<-- 绑定成功 --------------|                   |
 |                           |                           |                   |
 |-- 点击 Crypto 打赏 ------>|-- 创建 Anyway intent ---->|                   |
 |<-- 返回 payment_url -----|<-- 创建订单 --------------|                   |
 |                           |                           |                   |
 |-- 跳转 Anyway 完成链上支付 ----------------------------->|-- 链上 txHash --|
 |                           |                           |                   |
 |                           |<-- order.paid Webhook ----|                   |
 |                           |-- 查询 Base 链 receipt ----------------------->|
 |                           |-- 校验收款地址/金额 ------|                   |
 |                           |-- 入账并更新统计 ----------|                   |
 |<-- 页面轮询显示成功 ------|                           |                   |
```

## 7. 依赖与配置

新增 Python 依赖：

```txt
web3>=6.0.0
eth-account>=0.11.0
```

新增配置项（`.env`）：

```env
# Base 链 RPC
BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/...

# 打赏币种合约地址（留空表示 ETH / 原生币）
TIP_TOKEN_CONTRACT=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913  # USDC on Base
TIP_TOKEN_DECIMALS=6

# 链上确认数
TIP_CHAIN_CONFIRMATIONS=12

# EIP-712 签名域名
TIP_WALLET_SIGN_MESSAGE="我确认将地址 {address} 绑定为 Comedy Agent 的加密货币打赏地址，用于接收和支付打赏。"
```

## 8. 安全与风险

- **签名复用**：签名消息里加入时间戳或随机 nonce，避免同一签名被用于绑定多个账号。
- **链上校验**：不能只相信前端提交的 `tx_hash`，必须到链上读取 receipt 校验 `to` 和金额。
- **金额精度**：USDC 6 位小数，ETH 18 位；统一转换为 `cents` 或最小单位存储。
- **Webhook 幂等**：用 `anyway_order_id` + `tx_hash` 做幂等，防止重复入账。
- **地址一致性**：打赏意图生成时锁定 `payer_wallet` 和 `author_wallet`，链上校验必须匹配。

## 9. 开发任务拆分（建议顺序）

1. **数据层**：`user_profiles` 加钱包字段；新增 `crypto_tip_orders` 表；更新 `schema.py`、`models.py`、`medium_term.py`。
2. **钱包绑定接口**：`POST /me/wallet-address` 及 EIP-712 校验。
3. **前端钱包绑定 UI**：`me.html` 新增钱包卡片。
4. **创建打赏意图接口**：`POST /tips/crypto/intent`。
5. **链上校验服务**：封装 Base RPC 查询 receipt、校验地址/金额。
6. **入账处理**：Webhook / 手动确认 `/tips/crypto/confirm`、更新统计。
7. **前端广场打赏 UI**：`eval-square.html` 新增 Crypto 打赏标签页与支付后确认。
8. **统计接口 + UI**：`GET /tips/crypto/stats`、`/tips/crypto/orders` 与「我的」页面统计卡片。
9. **管理后台 UI**：`admin-console.html` 新增 Crypto 打赏订单列表与手动重试。
10. **测试**：绑定签名、创建意图、链上校验 mock、入账幂等、统计。

## 10. 与现有 Anyway 平台收款的关系

本方案定位为「Crypto 打赏」子流程，可与现有「Anyway 统一收款 + 后台提现」方案并存：

- 广场详情页同时保留「Anyway 打赏」（信用卡/稳定币）和「Crypto 打赏」（用户自管钱包）。
- 若后续确定全部走 Crypto，可下线平台收款流程。
