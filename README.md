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

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Keys

# 运行 CLI
comedy-agent
```

## 开发计划

详见 [plan.md](plan.md)。
