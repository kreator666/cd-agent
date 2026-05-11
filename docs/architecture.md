# Comedy Agent 架构图

## 一、系统分层架构

```mermaid
flowchart TB
    subgraph User["👤 用户"]
        U1["命令行终端"]
        U2["HTTP 客户端 / 前端"]
    end

    subgraph API["🌐 API 接入层"]
        CLI["CLI<br/>comedy-agent chat/run/skill<br/>(api/cli.py)"]
        Server["HTTP API<br/>FastAPI / Uvicorn<br/>(api/server.py)"]
    end

    subgraph Agent["🤖 Agent 核心层"]
        Orchestrator["AgentOrchestrator<br/>LangChain create_agent<br/>路由 & 调度<br/>(agent/orchestrator.py)"]
    end

    subgraph Skills["🛠️ Skill 技能层"]
        Base["ComedySkill 基类<br/>BaseTool + ABC<br/>(skills/base.py)"]
        Standup["StandupSkill<br/>脱口秀创作<br/>(skills/standup.py)"]
        Future1["相声创作<br/>(预留)"]
        Future2["小品创作<br/>(预留)"]
        Future3["笑点分析<br/>(预留)"]
    end

    subgraph Infra["⚙️ 基础设施层"]
        subgraph Models["🧠 模型层 (models/)"]
            Factory["ModelFactory<br/>统一模型工厂<br/>(models/factory.py)"]
            OpenAI["OpenAI<br/>GPT-4o / GPT-4o-mini"]
            Anthropic["Anthropic<br/>Claude 3.5 Sonnet"]
            Ollama["Ollama<br/>Llama3 / Qwen2.5"]
            Tongyi["通义千问<br/>qwen-max / plus"]
            Kimi["Moonshot / Kimi<br/>(OpenAI 兼容)"]
        end

        subgraph RAG["📚 RAG 知识库 (rag/)"]
            Retriever["ComedyRetriever<br/>混合检索<br/>(rag/retriever.py)<br/>🔜 第三阶段实现"]
        end

        subgraph Memory["🧩 记忆系统 (memory/)"]
            Store["MemoryStore<br/>用户偏好 & 历史<br/>(memory/store.py)<br/>🔜 第四阶段实现"]
        end

        subgraph Config["🔧 配置中心 (core/)"]
            Settings["Settings<br/>Pydantic BaseSettings<br/>(core/config.py)"]
            Env[".env<br/>环境变量"]
        end
    end

    U1 --> CLI
    U2 --> Server
    CLI --> Orchestrator
    Server --> Orchestrator
    Orchestrator --> Base
    Base --> Standup
    Base --> Future1
    Base --> Future2
    Base --> Future3
    Standup --> Factory
    Orchestrator --> Factory
    Factory --> OpenAI
    Factory --> Anthropic
    Factory --> Ollama
    Factory --> Tongyi
    Factory --> Kimi
    Factory --> Settings
    Settings --> Env
    Orchestrator -.-> Retriever
    Orchestrator -.-> Store
```

## 二、核心调用链路

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant CLI as CLI / HTTP API
    participant Orch as AgentOrchestrator
    participant Agent as LangChain Agent
    participant Skill as StandupSkill
    participant LLM as ModelFactory / LLM

    User->>CLI: "写一个关于职场加班的脱口秀"
    CLI->>Orch: run(user_input)
    Orch->>Orch: _build_agent()
    Orch->>Agent: create_agent(model, tools, system_prompt)
    Agent->>Agent: 意图识别 & 路由
    Agent->>Skill: invoke(topic="职场加班", style="...")
    Skill->>Skill: _build_prompt()
    Skill->>LLM: get_model()
    LLM-->>Skill: ChatModel 实例
    Skill->>LLM: chain.invoke(prompt)
    LLM-->>Skill: 生成的段子文本
    Skill-->>Agent: 段子结果
    Agent-->>Orch: {output, messages}
    Orch-->>CLI: result["output"]
    CLI-->>User: 完整脱口秀段子
```

## 三、模块依赖关系

```mermaid
flowchart LR
    cli["api/cli.py"] --> orch["agent/orchestrator.py"]
    srv["api/server.py"] --> orch
    orch --> factory["models/factory.py"]
    orch --> base["skills/base.py"]
    standup["skills/standup.py"] --> factory
    standup --> base
    factory --> cfg["core/config.py"]
    orch -.-> rag["rag/retriever.py"]
    orch -.-> mem["memory/store.py"]

    style rag fill:#ffcccc
    style mem fill:#ffcccc
```

> 🔜 标记为红色虚线框/虚线箭头的模块为**预留接口**，将在后续阶段实现。

## 四、技术栈

| 层级 | 技术选型 |
|------|----------|
| Agent 框架 | LangChain / LangGraph |
| LLM 接入 | OpenAI, Anthropic, Ollama, 通义千问, Moonshot/Kimi |
| Embedding | text-embedding-3-large / text-embedding-3-small |
| 向量数据库 | ChromaDB (开发) → Milvus (生产) |
| 记忆存储 | PostgreSQL / SQLite + Redis |
| HTTP 框架 | FastAPI + Uvicorn |
| CLI 框架 | argparse |
| 配置管理 | Pydantic Settings + python-dotenv |
