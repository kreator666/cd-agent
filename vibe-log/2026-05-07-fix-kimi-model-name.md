# 任务执行记录

## 任务信息
- **阶段**: 模型层修复
- **任务编号**: fix-3
- **任务名称**: 更正 Kimi 模型名称为 kimi-for-coding
- **执行日期**: 2026-05-07

## 任务说明
用户纠正：实际模型名称为 `kimi-for-coding`，而非 `kimi-k2-6`。

## 完成内容
- `factory.py`: 注册模型从 `kimi-k2-6` 更正为 `kimi-for-coding`
- `kimi-code` 别名保留，指向 `kimi-for-coding`
- 全量测试 **42/42 通过**

## 诊断备注
- 模型名称已更正，但 Moonshot API Key 测试仍为 `401 Invalid Authentication`
- 问题根源是 API Key 本身无效，非模型名称问题
- 建议用户检查 Key 是否来自 [Moonshot 控制台](https://platform.moonshot.cn/)

## Commit 记录
- **Commit ID**: `3bfe38d66bf0b2df41a45f236149aa2f68f8326b`
- **Commit Message**: `fix: 更正 Kimi 模型名称为 kimi-for-coding`
- **Branch**: `feature`
- **Remote**: `origin/feature`
