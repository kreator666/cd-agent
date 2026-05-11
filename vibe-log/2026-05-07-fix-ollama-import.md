# 任务执行记录

## 任务信息
- **阶段**: 紧急修复
- **任务编号**: fix-2
- **任务名称**: 升级 Ollama 导入并增强运行时错误提示
- **执行日期**: 2026-05-07

## 问题描述
用户运行 `comedy-agent chat --model ollama-llama3` 时遇到：
1. `LangChainDeprecationWarning`: `ChatOllama` 在 LangChain 0.3.1 中已弃用
2. `NotImplementedError`: 旧版 `ChatOllama` 不支持 `bind_tools`
3. 更换新版后，Ollama 服务未运行时抛出 502 错误，用户无感知

## 修复内容
- `factory.py`: 
  - 优先从 `langchain_ollama` 导入 `ChatOllama`
  - 保留 `langchain_community` 兼容回退
  - 未安装 `langchain-ollama` 时给出明确安装提示
- `cli.py`:
  - 新增 `_print_runtime_error`，专门处理 Ollama 连接错误
  - 502 错误时提示用户：下载 Ollama → 启动服务 → 拉取模型，或切换云端模型
- 安装 `langchain-ollama` + `anthropic` 依赖
- 全量测试 **42/42 通过**

## Commit 记录
- **Commit ID**: `c8838df31fccf1ca7f5b3b2d5d3902c348d47707`
- **Commit Message**: `fix: 升级 Ollama 导入至 langchain-ollama 并增强运行时错误提示`
- **Branch**: `feature`
- **Remote**: `origin/feature`

## 备注
- Ollama 本地模型需额外安装 Ollama 服务，不属于 pip 依赖
- 用户未启动 Ollama 时现在会看到：
  ```
  ❌ 无法连接到 Ollama 服务。
  请先安装并启动 Ollama：
    1. 下载安装：https://ollama.com/download
    2. 启动服务：ollama serve
    3. 拉取模型：ollama pull llama3
  或使用云端模型：--model gpt-4o / claude-3-5-sonnet
  ```
