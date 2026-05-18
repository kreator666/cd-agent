# Comedy Agent（喜剧行业垂直 Agent）

基于 LangChain 的一体化 Agent 框架，专注于喜剧创作辅助。

## 技术栈

- **Agent 框架**: LangChain
- **模型接入**: ModelFactory 统一封装（OpenAI / Anthropic / Ollama / 通义千问）
- **向量数据库**: ChromaDB（开发）→ Milvus（生产）
- **记忆存储**: PostgreSQL / SQLite + Redis
- **文档解析**: Unstructured / LangChain DocumentLoader
- **检索增强**: BM25 + Cross-Encoder 重排序
- **可观测性**: LangSmith / 自建日志

## 项目结构

```
cd-agent/
├── src/comedy_agent/      # 核心源码
│   ├── core/              # 配置与通用工具
│   ├── models/            # ModelFactory 模型层
│   ├── skills/            # Skill 基类与内置技能
│   ├── agent/             # Agent 主控与 Orchestrator
│   ├── rag/               # RAG 检索与知识库
│   ├── memory/            # 记忆系统
│   └── api/               # CLI / HTTP API
├── skills/                # 插件化 Skill 目录
├── data/                  # 数据目录
├── tests/                 # 测试
└── vibe-log/              # 开发日志
```

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
comedy-agent chat --model claude-3-5-sonnet
comedy-agent chat --model gpt-4o
comedy-agent chat --model ollama-llama3   # 本地模型，无需 API Key

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
# 全量测试
python -m pytest tests/ -v
```

## 开发计划

详见 [plan.md](plan.md)。
