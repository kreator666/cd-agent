# Comedy Agent（喜剧行业垂直 Agent）

基于 LangChain 的一体化 Agent 框架，专注于喜剧创作辅助。支持多模型接入、RAG 知识库检索、个性化记忆、学习模式与插件化 Skill 生态。

## 技术栈

- **Agent 框架**: LangChain / LangGraph
- **模型接入**: ModelFactory 统一封装（OpenAI / Anthropic / Ollama / 通义千问 / Moonshot）
- **向量数据库**: ChromaDB（持久化）+ HuggingFace `all-MiniLM-L6-v2` Embedding
- **记忆存储**: SQLite（SQLModel）+ 中期记忆上下文注入
- **文档解析**: Unstructured / LangChain DocumentLoader（支持 PDF/Word/网页/文本/SRT/VTT/ASS 字幕）
- **检索增强**: 向量检索（ChromaDB）+ BM25 关键词检索 + Cross-Encoder 重排序
- **可观测性**: LangSmith / 自建 Metrics + Tracer

## 当前功能特性

| 特性 | 状态 | 说明 |
|------|------|------|
| 多模型接入 | ✅ 已完成 | 支持 OpenAI、Anthropic、Ollama、通义千问、Moonshot/Kimi，自动 Fallback 降级 |
| 内置 Skill | ✅ 已完成 | 8 个：脱口秀、相声、小品、情景喜剧、漫才、日式短剧、笑点分析、剧本评估 |
| 插件化 Skill | ✅ 已完成 | 从 `skills/` 目录动态加载声明式 / 代码式 Skill，支持热重载 |
| Agent 主控 | ✅ 已完成 | 基于 LangGraph 的 Orchestrator，自动路由用户请求到对应 Skill |
| CLI 交互 | ✅ 已完成 | `chat`、`run`、`skills`、`skill standup` 等命令 |
| HTTP API | ✅ 已完成 | FastAPI 服务，覆盖创作、学习、管理、调试全链路 |
| RAG 知识库 | ✅ 已完成 | 默认库 + 个人库联合检索，Skill 内部自动注入知识 |
| 记忆系统 | ✅ 已完成 | 用户偏好、历史对话、作品库，自动提取并注入上下文 |
| 文档上传 | ✅ 已完成 | 支持 PDF/Word/网页/文本/字幕，自动分块入库个人知识库 |
| 学习模式 | ✅ 已完成 | 交互式问答（explain/analyze/extract）+ 技巧卡片库 |
| 作品管理 | ✅ 已完成 | 保存、查看、评分、删除历史剧本 |
| Prompt 工程化 | ✅ 已完成 | 统一管理、外部模板热加载、变量注入 |
| 前端页面 | ✅ 已完成 | 8 个独立页面，统一导航 |

## 项目结构

```
cd-agent/
├── src/comedy_agent/      # 核心源码
│   ├── core/              # 配置与通用工具（PromptManager、Settings、Tracer/Metrics）
│   ├── models/            # ModelFactory 模型层（LLM + Embedding）
│   ├── skills/            # Skill 基类与内置技能（8 个）
│   ├── agent/             # Agent 主控与 Orchestrator
│   ├── rag/               # RAG 检索与知识库（Retriever、VectorStore、Ingestor）
│   ├── memory/            # 记忆系统（Schema、UnifiedMemory、PreferenceExtractor）
│   └── api/               # CLI / HTTP API
├── frontend/              # 前端页面（8 个 HTML）
├── skills/                # 插件化 Skill 目录
├── data/                  # 数据目录（SQLite、ChromaDB、Prompt 模板、上传文档）
├── tests/                 # 测试（402 个用例）
└── vibe-log/              # 开发日志
```

## 开发进度

| 阶段 | 主题 | 进度 | 核心目标 |
|------|------|------|----------|
| 第一阶段 | MVP 骨架搭建 | ✅ 已完成 | 跑通 Agent → Skill → LLM → Output 的最小闭环 |
| 第二阶段 | Skill 体系与模型层 | ✅ 已完成 | 构建完整喜剧 Skill 生态，支持模型动态切换与 Fallback |
| 第三阶段 | RAG 知识库建设 | ✅ 已完成 | 让 Agent 具备喜剧行业专业知识检索与注入能力 |
| 第四阶段 | 记忆系统与用户层 | ✅ 已完成 | 实现个性化记忆与持续进化 |
| 第五阶段 | 工程化与优化 | ⏳ 进行中 | 性能、可观测性、前端体验完善 |

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
| `EMBEDDING_MODEL` | Embedding 模型 | `hf-local`（默认，本地 HuggingFace） |
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
```

**核心接口列表：**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/skills` | 列出所有 Skill |
| POST | `/skills/install` | 安装新 Skill |
| DELETE | `/skills/{name}` | 卸载 Skill |
| POST | `/skills/reload` | 热重载插件 |
| POST | `/chat` | 对话创作（Agent 路由 + RAG + 记忆） |
| POST | `/skills/standup` | 脱口秀创作 |
| POST | `/skills/sketch` | 小品创作 |
| POST | `/skills/manzai` | 漫才创作 |
| POST | `/skills/japanese-sketch` | 日式短剧创作 |
| POST | `/scripts` | 保存作品 |
| GET | `/scripts` | 列出作品 |
| PATCH | `/scripts/{id}/rate` | 作品评分 |
| POST | `/documents/upload` | 上传文档到个人知识库 |
| GET | `/documents` | 列出上传的文档 |
| POST | `/learn/chat` | 学习模式对话（explain/analyze/extract） |
| POST | `/learn/cards` | 创建技巧卡片 |
| GET | `/learn/cards` | 列出技巧卡片 |
| POST | `/debug/retrieve` | 调试知识库检索过程 |
| POST | `/evaluate/script` | 剧本评估 |
| GET | `/models` | 列出可用模型 |
| GET | `/preferences` | 获取用户偏好 |

### 5. 前端页面

启动 API 服务后，直接打开 `frontend/index.html` 即可使用：

| 页面 | 路径 | 说明 |
|------|------|------|
| 创作主页面 | `frontend/index.html` | 聊天创作，支持模型切换、快捷指令、历史会话 |
| Skill 管理 | `frontend/skills.html` | 查看、安装、卸载、热重载 Skill |
| 我的 | `frontend/me.html` | 个人中心入口 |
| 知识库 | `frontend/knowledge.html` | 上传文档、查看已上传文件 |
| 技巧库 | `frontend/cards.html` | 创建/查看/删除技巧卡片 |
| 偏好设置 | `frontend/preferences.html` | 查看和编辑用户偏好 |
| 作品管理 | `frontend/scripts.html` | 查看、评分、删除作品 |

### 6. 运行测试

```bash
# 全量测试（当前 402 个用例）
python -m pytest tests/ -v
```

## 内置 Skill 一览

| Skill | 类型 | 任务类型 | 说明 |
|-------|------|----------|------|
| `standup_generator` | 创作 | creative | 脱口秀创作：主题、风格、时长、受众、笑点密度、多视角 |
| `crosstalk_generator` | 创作 | creative | 相声创作：逗哏、捧哏、风格、篇幅 |
| `sketch_generator` | 创作 | creative | 小品创作：主题、角色数、场景、冲突类型 |
| `sitcom_generator` | 创作 | creative | 情景喜剧创作：情景、集主题、角色、场景数 |
| `manzai_generator` | 创作 | creative | 漫才创作：话题、时长、段落数、荒谬等级 |
| `japanese_sketch_generator` | 创作 | creative | 日式短剧创作：主题、角色数、极端性格、笑点密度 |
| `joke_analyzer` | 分析 | analytical | 笑点分析：拆解笑点结构与节奏 |
| `script_evaluator` | 分析 | analytical | 剧本评估：多维度评分与改进建议 |

所有创作类 Skill 均支持 **RAG 知识库注入**：根据 topic/theme 自动检索默认知识库 + 用户个人知识库，将相关知识拼接到 System Prompt 中指导创作。

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
- [docs/architecture.md](docs/architecture.md) — 系统架构图与说明
