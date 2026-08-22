# 任务执行记录

## 任务信息
- **阶段**: 打赏 / 支付
- **任务编号**: fix-anyway-amount-units
- **任务名称**: 修正 Anyway 订单金额单位换算
- **执行日期**: 2026-08-22

## 任务说明
Anyway 在 crypto 场景下返回的 `amountCents` 实际为币种最小单位（如 USDC 为 6 位小数的 micro-units），但原有实现直接将其视为美分，导致金额被放大 10000 倍，进而使手续费/净得计算错误。

## 完成内容
- 在 `src/comedy_agent/api/routers/anyway_webhook.py` 新增 `_anyway_amount_to_cents` 辅助函数，按币种精度（USD 2 位、USDC/USDT 6 位）统一换算为美分
- Webhook 处理 `order.paid` 时同步更新 `tip_record` 的 `amount_cents` / `currency` / `fee_cents` / `net_amount_cents`
- 扩展 `update_tip_record_status` 接口（`store.py` / `medium_term.py` / `unified.py`）支持更新金额与币种
- 新增 `scripts/migrate_fix_anyway_tip_units.py` 脚本，拉取 Anyway 实际订单并修正历史数据及对应收益记录
- 运行迁移脚本，2 笔已支付订单 currency 由 `usd` 修正为 `usdc`，金额/手续费/净得保持正确

## Commit 记录
- **Commit ID**: `291d9908d8a5cc0e2bd22c21e918a6f341918eca`
- **Commit Message**: `fix(tips): 修正 Anyway 订单金额单位换算`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 测试通过率: 24/24 (100%)
- 已有两笔支付成功订单（ORD26WZE6S1L25KTD、ORD261SI5IABFQ21D）在迁移后数据正确：1 USDC 对应 100 美分，手续费 5 美分，净得 95 美分
- 需要重启服务使新代码生效
