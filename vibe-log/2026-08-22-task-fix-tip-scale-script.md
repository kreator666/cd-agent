# 任务执行记录

## 任务信息
- **阶段**: 打赏 / 数据修复
- **任务编号**: fix-tip-scale-script
- **任务名称**: 增加打赏记录金额缩放脚本
- **执行日期**: 2026-08-22

## 任务说明
针对用户反馈的特定时间点的打赏记录手续费/净得金额被放大 1000 倍的问题，创建一个可复用的数据修复脚本。

## 完成内容
- 新增 `scripts/fix_tip_amount_scale.py`
  - 按时间窗口或 `tip_id` 匹配打赏记录
  - 将 `fee_cents` / `net_amount_cents` 按指定倍数缩放（默认 1000）
  - 可选同时缩放 `amount_cents`
  - 支持 `--dry-run` 预览
  - 同步删除并重建对应的 `tip_anyway` 收益记录，保持收益余额一致
- 列出当前打赏记录核对：3 条记录金额已正确（1 USDC -> 100 美分，fee 5，net 95）

## Commit 记录
- **Commit ID**: `38e99c6892c723b7d3c570df864e69f78a89cd9e`
- **Commit Message**: `feat(scripts): 增加打赏记录金额缩放脚本`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 当前数据库中 2026/8/22 10:30:06 和 09:44:21 附近没有匹配到打赏记录；如这些时间来自其他时区或历史数据已删除，可使用 `--window` 扩大窗口或用 `--tip-id` 直接指定
- 用法示例：`python scripts/fix_tip_amount_scale.py --dry-run "2026/8/22 10:30:06" "2026/8/22 09:44:21"`
