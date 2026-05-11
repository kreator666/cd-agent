# 任务执行记录

## 任务信息
- **阶段**: 文档更新
- **任务编号**: docs-1
- **任务名称**: 更新 README 使用示例与依赖安装说明
- **执行日期**: 2026-05-07

## 任务说明
将使用示例和依赖安装的库的命令写入 README。

## 完成内容
- 重写 README.md「快速开始」章节
- 新增内容：
  - 核心依赖 + 可选依赖安装命令（`langchain-anthropic`, `langchain-ollama`）
  - 环境变量配置表（OPENAI_API_KEY / ANTHROPIC_API_KEY / DASHSCOPE_API_KEY / DEFAULT_MODEL / VECTOR_DB_PATH）
  - CLI 完整使用示例（`--version`, `chat`, `run`, `skills`, `skill standup`）
  - 模型切换示例（gpt-4o / claude-3-5-sonnet / ollama-llama3）
  - HTTP API 启动方式与接口列表
  - 测试运行命令 `pytest tests/ -v`

## Commit 记录
- **Commit ID**: `38bc18205a6a68e368e2637d5870da97b2adee9e`
- **Commit Message**: `docs: 更新 README 使用示例与依赖安装说明`
- **Branch**: `feature`
- **Remote**: `origin/feature`

## 备注
- 无代码变更，纯文档更新
- README 已可直接指导新用户完成环境配置与首次运行
