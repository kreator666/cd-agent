# Comedy Agent（喜剧行业垂直 Agent）

基于 LangChain 的一体化 Agent 框架，专注于喜剧创作辅助。

## 技术栈

- **Agent 框架**: LangChain / LangGraph
- **模型接入**: ModelFactory 统一封装（OpenAI / Anthropic / Ollama / 通义千问 / Moonshot）
- **向量数据库**: ChromaDB（开发）→ Milvus（生产）— *预留接口*
- **记忆存储**: PostgreSQL / SQLite + Redis — *预留接口*
- **文档解析**: Unstructured / LangChain DocumentLoader — *预留接口*
- **检索增强**: BM25 + Cross-Encoder 重排序 — *预留接口*
- **可观测性**: LangSmith / 自建日志 — *预留接口*

## 当前功能特性

| 特性 | 状态 | 说明 |
|------|------|------|
| 多模型接入 | ✅ 已完成 | 支持 OpenAI、Anthropic、Ollama、通义千问、Moonshot/Kimi，自动 Fallback 降级 |
| 内置 Skill | ✅ 已完成 | 脱口秀、相声、小品、情景喜剧、笑点分析、剧本评估 |
| 插件化 Skill | ✅ 已完成 | 从 `skills/` 目录动态加载声明式 / 代码式 Skill |
| Agent 主控 | ✅ 已完成 | 基于 LangGraph 的 Orchestrator，自动路由用户请求到对应 Skill |
| CLI 交互 | ✅ 已完成 | `chat`、`run`、`skills`、`skill standup` 等命令 |
| HTTP API | ✅ 已完成 | FastAPI 服务，`/health`、`/skills`、`/chat`、`/skills/standup` |
| Prompt 工程化 | ✅ 已完成 | 统一管理、变量注入、版本管理、A/B 测试 |
| RAG 知识库 | ⏳ 预留接口 | `ComedyRetriever` 已预留，待第三阶段实现 |
| 记忆系统 | ⏳ 预留接口 | `MemoryStore` 已预留，待第四阶段实现 |

## 项目结构

```
cd-agent/
├── src/comedy_agent/      # 核心源码
│   ├── core/              # 配置与通用工具（PromptManager、Settings）
│   ├── models/            # ModelFactory 模型层（LLM + Embedding）
│   ├── skills/            # Skill 基类与内置技能（6 个）
│   ├── agent/             # Agent 主控与 Orchestrator
│   ├── rag/               # RAG 检索与知识库（预留接口）
│   ├── memory/            # 记忆系统（预留接口）
│   └── api/               # CLI / HTTP API
├── skills/                # 插件化 Skill 目录
├── data/                  # 数据目录
├── tests/                 # 测试（78 个用例全部通过）
└── vibe-log/              # 开发日志
```

## 开发进度

| 阶段 | 主题 | 进度 | 核心目标 |
|------|------|------|----------|
| 第一阶段 | MVP 骨架搭建 | ✅ 已完成 | 跑通 Agent → Skill → LLM → Output 的最小闭环 |
| 第二阶段 | Skill 体系与模型层 | ✅ 已完成 | 构建完整喜剧 Skill 生态，支持模型动态切换与 Fallback |
| 第三阶段 | RAG 知识库建设 | ⏳ 未开始 | 让 Agent 具备喜剧行业专业知识检索与注入能力 |
| 第四阶段 | 记忆系统与用户层 | ⏳ 未开始 | 实现个性化记忆与持续进化 |
| 第五阶段 | 工程化与优化 | ⏳ 未开始 | 性能、可观测性、生产就绪 |

> 详见 [plan.md](plan.md)。

## 快速开始

### 1. 安装依赖

```bash
# 核心依赖
pip install -e ".[dev]"

# 可选：Anthropic 模型支持
pip install langchain-anthropic

# 可选：Ollama 本地模型支持（需额外安装 Ollama 服务）
pip install langchain-ollama

# 注意：交互模式需要支持 Tool Calling 的模型
# 推荐：llama3.1 / qwen2.5（llama3 不支持 Tool Calling）
ollama pull llama3.1
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你需要的 API Keys
```

支持的环境变量：

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `OPENAI_API_KEY` | OpenAI API Key | `sk-xxx` |
| `ANTHROPIC_API_KEY` | Anthropic API Key | `sk-ant-xxx` |
| `DASHSCOPE_API_KEY` | 阿里云通义千问 Key | `sk-xxx` |
| `MOONSHOT_API_KEY` | Moonshot / Kimi API Key | `sk-kimi-xxx` |
| `DEFAULT_MODEL` | 默认模型 | `gpt-4o` |
| `CREATIVE_MODEL` | 创意任务模型 | `claude-3-5-sonnet` |
| `ANALYTICAL_MODEL` | 分析任务模型 | `gpt-4o` |
| `FAST_MODEL` | 快速响应模型 | `gpt-4o-mini` |
| `CREATIVE_FALLBACK_MODELS` | 创意任务备用模型链 | `gpt-4o,qwen-max` |
| `ANALYTICAL_FALLBACK_MODELS` | 分析任务备用模型链 | `qwen-max,gpt-4o-mini` |
| `FAST_FALLBACK_MODELS` | 快速任务备用模型链 | `qwen-turbo,ollama-qwen2.5` |
| `VECTOR_DB_PATH` | 向量数据库路径 | `./chroma_data` |

### 3. CLI 使用

```bash
# 查看版本
comedy-agent --version

# 全局指定模型（可被子命令的 --model 覆盖）
comedy-agent --model gpt-4o chat

# 交互式对话（默认模型）
comedy-agent chat

# 指定模型对话
#ollama run qwen2.5 
#ollama rm llama3:latest gemma2:9b mistral:latest
#comedy-agent chat --model  ollama-qwen2.5
comedy-agent chat --model claude-3-5-sonnet
comedy-agent chat --model gpt-4o
comedy-agent chat --model ollama-llama3.1   # 本地模型，无需 API Key

# 单次运行
comedy-agent run "写一个关于相亲的脱口秀" --model gpt-4o

# 列出可用 Skill（含内置 Skill 与插件 Skill）
comedy-agent skills

# 直接调用脱口秀创作 Skill
comedy-agent skill standup --topic "职场加班" --style "自嘲" --duration 5 --audience "通用"
```

**完整命令列表：**

| 命令 | 说明 | 示例 |
|------|------|------|
| `--version` | 显示版本号 | `comedy-agent --version` |
| `--model` | 全局指定模型 | `comedy-agent --model gpt-4o chat` |
| `chat` | 交互式对话 | `comedy-agent chat --model claude-3-5-sonnet` |
| `run` | 单次运行 | `comedy-agent run "写一段脱口秀" --model gpt-4o` |
| `skills` | 列出所有可用 Skill | `comedy-agent skills` |
| `skill standup` | 直接调用脱口秀创作 | `comedy-agent skill standup --topic "职场" --style "自嘲" --duration 5` |

### 4. HTTP API 服务

```bash
# 启动服务
uvicorn comedy_agent.api.server:app --reload

# 接口列表
# GET  /health          健康检查
# GET  /skills          列出 Skill
# POST /chat            对话
# POST /skills/standup  脱口秀创作
```

### 5. 运行测试

```bash
# 全量测试（当前 78 个用例全部通过）
python -m pytest tests/ -v
```

## 内置 Skill 一览

| Skill | 类型 | 任务类型 | 说明 |
|-------|------|----------|------|
| `standup` | 创作 | creative | 脱口秀创作：主题、风格、时长、受众 |
| `crosstalk` | 创作 | creative | 相声创作：逗哏、捧哏、结构 |
| `sketch` | 创作 | creative | 小品创作：角色、场景、冲突 |
| `sitcom` | 创作 | creative | 情景喜剧创作：集数、角色关系 |
| `joke_analyzer` | 分析 | analytical | 笑点分析：拆解笑点结构与节奏 |
| `script_evaluator` | 分析 | analytical | 剧本评估：评分与改进建议 |

## 模型支持矩阵

| 提供商 | 模型 | 需要 API Key | 支持 Tool Calling |
|--------|------|--------------|-------------------|
| OpenAI | gpt-4o, gpt-4o-mini, gpt-4-turbo | ✅ | ✅ |
| Anthropic | claude-3-5-sonnet, claude-3-opus, claude-3-5-haiku | ✅ | ✅ |
| 通义千问 | qwen-max, qwen-plus, qwen-turbo | ✅ | ✅ |
| Moonshot | kimi-for-coding | ✅ | ✅ |
| Ollama | ollama-llama3.1, ollama-qwen2.5, ollama-llama3 | ❌ | llama3.1/qwen2.5 ✅ |

## 设计文档

- [comedy-agent-design.md](comedy-agent-design.md) — 设计方案与核心问题解答
- [plan.md](plan.md) — 详细开发计划与任务分解
