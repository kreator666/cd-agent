# 任务执行记录

## 任务信息
- **阶段**: 紧急修复
- **任务编号**: fix-1
- **任务名称**: 模型配置错误友好提示与 CLI/Server 容错
- **执行日期**: 2026-05-07

## 问题描述
用户运行 `comedy-agent chat` 时遇到：
1. `langchain-anthropic` 未安装（警告）
2. `OPENAI_API_KEY` 未设置导致程序直接崩溃（`openai.OpenAIError`）

## 修复内容
- `ModelFactory`: 新增 `ModelConfigError` 异常类
- OpenAI / Anthropic / Qwen 模型构造器提前校验 API Key：
  - Key 为空时抛出 `ModelConfigError`，提示具体环境变量名和本地模型替代方案
- `cli.py`: `_build_orchestrator` 捕获 `ModelConfigError`，打印友好错误后退出
- `server.py`: `lifespan` 捕获 `ModelConfigError`，记录错误日志而非崩溃
- 新增 `test_model_config_error_message` 单元测试
- 全量测试 **42/42 通过**

## Commit 记录
- **Commit ID**: `fca4e25693a48f50c6d8769e449faa41beeb06ac`
- **Commit Message**: `fix: 模型配置错误友好提示与 CLI/Server 容错`
- **Branch**: `feature`
- **Remote**: `origin/feature`

## 备注
- 用户现在未配置 API Key 时会看到：
  ```
  ❌ 模型配置错误

  模型 'gpt-4o' 需要 OpenAI API Key。
  请设置环境变量：export OPENAI_API_KEY=sk-xxx
  或使用本地模型：--model ollama-llama3
  ```
- `langchain-anthropic` 未安装属于可选依赖，不影响核心功能
