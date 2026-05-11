# 任务执行记录

## 任务信息
- **任务名称**: 更新 README —— CLI 命令与环境变量
- **执行日期**: 2026-05-11

## 完成内容
- 梳理 CLI 所有命令及参数：
  - `--version` / `--model`（全局参数）
  - `chat [--model]`（交互式对话）
  - `run <prompt> [--model]`（单次运行）
  - `skills`（列出 Skill）
  - `skill standup --topic --style --duration --audience`（直接调用 Skill）
- README.md 更新：
  - 新增完整命令列表表格（命令 / 说明 / 示例）
  - 补充环境变量：`MOONSHOT_API_KEY`、模型分层配置（`CREATIVE_MODEL` / `ANALYTICAL_MODEL` / `FAST_MODEL`）、Fallback 备用链配置
  - 更新 CLI 使用示例，增加 `--model` 全局参数用法

## Commit 记录
- **Commit ID**: `69e009a`
- **Commit Message**: `docs(readme): update CLI commands and environment variables`
- **Branch**: `feature`
- **Remote**: `origin/feature`
