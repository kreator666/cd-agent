# Comedy Agent 架构图

## 一、系统分层架构

```mermaid
flowchart TB
    subgraph User["👤 用户"]
        U1["命令行终端"]
        U2["浏览器 / HTTP 客户端"]
    end

    subgraph Frontend["🖥️ 前端层 (frontend/)"]
        F1["index.html · 创作聊天"]
        F2["skills.html · Skill 管理"]
        F3["knowledge.html · 知识库"]
        F4["cards.html · 技巧库"]
        F5["scripts.html · 作品管理"]
        F6["me.html · 个人中心"]
    end

    subgraph API["🌐 API 接入层 (api/)"]
        CLI["CLI<br/>comedy-agent chat/run/skill<br/>(api/cli.py)"]
        Server["HTTP API<br/>FastAPI / Uvicorn<br/>(api/server.py)"]
    end

    subgraph Agent["🤖 Agent 核心层 (agent/)"]
        Orchestrator["AgentOrchestrator<br/>LangChain create_agent<br/>路由 & 调度 + RAG + 记忆注入<br/>(agent/orchestrator.py)"]
    end

    subgraph Skills["🛠️ Skill 技能层 (skills/)"]
        Base["ComedySkill 基类<br/>BaseTool + RAG 检索能力<br/>(skills/base.py)"]
        Standup["StandupSkill<br/>脱口秀"]
        Crosstalk["CrosstalkSkill<br/>相声"]
        Sketch["SketchSkill<br/>小品"]
        Sitcom["SitcomSkill<br/>情景喜剧"]
        Manzai["ManzaiSkill<br/>漫才"]
        JSketch["JapaneseSketchSkill<br/>日式短剧"]
        Joke["JokeAnalyzerSkill<br/>笑点分析"]
        Eval["ScriptEvaluatorSkill<br/>剧本评估"]
    end

    subgraph Infra["⚙️ 基础设施层"]
        subgraph Models["🧠 模型层 (models/)"]
            Factory["ModelFactory<br/>统一模型工厂<br/>(models/factory.py)"]
            OpenAI["OpenAI<br/>GPT-4o / GPT-4o-mini"]
            Anthropic["Anthropic<br/>Claude 3.5 Sonnet"]
            Ollama["Ollama<br/>Llama3.1 / Qwen2.5"]
            Tongyi["通义千问<br/>qwen-max / plus"]
            Kimi["Moonshot / Kimi"]
            Embed["HuggingFace<br/>all-MiniLM-L6-v2<br/>(hf-local)"]
        end

        subgraph RAG["📚 RAG 知识库 (rag/)"]
            Retriever["ComedyRetriever<br/>混合检索<br/>(rag/retriever.py)"]
            VStore["VectorStore<br/>ChromaDB<br/>(rag/vector_store.py)"]
            Ingestor["KnowledgeIngestor<br/>文档解析 & 分块<br/>(rag/ingest.py)"]
            UserColl["个人知识库<br/>user_knowledge_{uid}"]
            DefaultColl["默认知识库<br/>comedy_knowledge"]
        end

        subgraph Memory["🧩 记忆系统 (memory/)"]
            UMem["UnifiedMemory<br/>统一记忆接口<br/>(memory/unified.py)"]
            Schema["SQLModel Schema<br/>UserProfile / Preference /<br/>Conversation / Script<br/>(memory/schema.py)"]
            Extractor["PreferenceExtractor<br/>偏好自动提取<br/>(memory/preference_extractor.py)"]
        end

        subgraph Config["🔧 配置中心 (core/)"]
            Settings["Settings<br/>Pydantic BaseSettings<br/>(core/config.py)"]
            PromptMgr["PromptManager<br/>外部模板热加载<br/>(core/prompt_manager.py)"]
            Env[".env<br/>环境变量"]
        end
    end

    U1 --> CLI
    U2 --> Frontend
    Frontend --> Server
    CLI --> Orchestrator
    Server --> Orchestrator
    Orchestrator --> Base
    Base --> Standup
    Base --> Crosstalk
    Base --> Sketch
    Base --> Sitcom
    Base --> Manzai
    Base --> JSketch
    Base --> Joke
    Base --> Eval
    Standup --> Factory
    Sketch --> Factory
    Manzai --> Factory
    Orchestrator --> Factory
    Factory --> OpenAI
    Factory --> Anthropic
    Factory --> Ollama
    Factory --> Tongyi
    Factory --> Kimi
    Factory --> Embed
    Factory --> Settings
    Settings --> Env
    Settings --> PromptMgr
    Orchestrator --> Retriever
    Retriever --> VStore
    VStore --> UserColl
    VStore --> DefaultColl
    Server --> Ingestor
    Ingestor --> VStore
    Orchestrator --> UMem
    UMem --> Schema
    Server --> Schema
    UMem --> Extractor
```

## 二、核心调用链路（含 RAG 注入）

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant API as CLI / HTTP API / 前端
    participant Orch as AgentOrchestrator
    participant RAG as RAG 检索
    participant Mem as 记忆系统
    participant Skill as Skill（如 StandupSkill）
    participant LLM as ModelFactory / LLM

    User->>API: "写一个关于职场加班的脱口秀"
    API->>Orch: run(user_input, user_id)
    Orch->>RAG: _build_system_prompt()
    RAG->>RAG: 检索默认库 + 个人库
    RAG-->>Orch: 知识库结果注入 system prompt
    Orch->>Mem: build_context_text(user_id)
    Mem-->>Orch: 用户偏好 & 历史作品
    Orch->>Orch: 组装完整 system prompt
    Orch->>Orch: _build_agent()
    Orch->>Skill: invoke(topic="职场加班", user_id=...)
    Skill->>Skill: _retrieve_knowledge(topic)
    Skill->>RAG: 检索知识库
    RAG-->>Skill: 相关知识片段
    Skill->>Skill: 拼接 SYSTEM_PROMPT + 知识库
    Skill->>LLM: get_model_with_fallback()
    LLM-->>Skill: ChatModel 实例
    Skill->>LLM: chain.invoke(prompt)
    LLM-->>Skill: 生成的段子文本
    Skill-->>Orch: 段子结果
    Orch->>Mem: extract_preferences()
    Orch-->>API: result["output"]
    API-->>User: 完整脱口秀段子
```

## 三、RAG 知识库数据流

```mermaid
flowchart LR
    subgraph Input["📥 输入"]
        PDF["PDF / Word"]
        Web["网页 / 文本"]
        Sub["SRT / VTT / ASS 字幕"]
    end

    subgraph Ingest["🔧 解析入库 (rag/ingest.py)"]
        Loader["DocumentLoader<br/>多格式解析"]
        Chunker["文本分块<br/>保留时间码元数据"]
        Embed["Embedding<br/>all-MiniLM-L6-v2"]
    end

    subgraph Storage["💾 存储"]
        UserDB[(个人库<br/>user_knowledge_{uid})]
        DefaultDB[(默认库<br/>comedy_knowledge)]
    end

    subgraph Retrieval["🔍 检索 (rag/retriever.py)"]
        VecSearch["向量检索<br/>ChromaDB"]
        BM25["BM25<br/>关键词检索"]
        Merge["合并去重"]
        Rerank["Cross-Encoder<br/>重排序"]
    end

    subgraph Consume["🎯 消费"]
        AgentSys["Agent System Prompt<br/>决策层注入"]
        SkillSys["Skill System Prompt<br/>创作层注入"]
    end

    PDF --> Loader
    Web --> Loader
    Sub --> Loader
    Loader --> Chunker
    Chunker --> Embed
    Embed --> UserDB
    Embed --> DefaultDB
    UserDB --> VecSearch
    DefaultDB --> VecSearch
    VecSearch --> Merge
    BM25 --> Merge
    Merge --> Rerank
    Rerank --> AgentSys
    Rerank --> SkillSys
```

## 四、模块依赖关系

```mermaid
flowchart LR
    cli["api/cli.py"] --> orch["agent/orchestrator.py"]
    srv["api/server.py"] --> orch
    orch --> factory["models/factory.py"]
    orch --> base["skills/base.py"]
    orch --> retriever["rag/retriever.py"]
    orch --> memory["memory/unified.py"]
    orch --> vstore["rag/vector_store.py"]
    standup["skills/standup.py"] --> factory
    standup --> base
    sketch["skills/sketch.py"] --> factory
    sketch --> base
    manzai["skills/manzai.py"] --> factory
    manzai --> base
    js["skills/japanese_sketch.py"] --> factory
    js --> base
    factory --> cfg["core/config.py"]
    memory --> schema["memory/schema.py"]
    retriever --> vstore
    ingest["rag/ingest.py"] --> vstore
    ingest --> factory

    style orch fill:#FFF8E1,stroke:#FF9800,stroke-width:2px
    style base fill:#D4EDDA,stroke:#28A745,stroke-width:2px
    style retriever fill:#D4EDDA,stroke:#28A745,stroke-width:2px
    style memory fill:#D4EDDA,stroke:#28A745,stroke-width:2px
    style vstore fill:#D4EDDA,stroke:#28A745,stroke-width:2px
    style ingest fill:#D4EDDA,stroke:#28A745,stroke-width:2px
```

## 五、技术栈

| 层级 | 技术选型 |
|------|----------|
| Agent 框架 | LangChain / LangGraph |
| LLM 接入 | OpenAI, Anthropic, Ollama, 通义千问, Moonshot/Kimi |
| Embedding | HuggingFace `all-MiniLM-L6-v2`（本地，384维）|
| 向量数据库 | ChromaDB（持久化） |
| 记忆存储 | SQLite + SQLModel（开发）/ PostgreSQL（生产） |
| 文档解析 | Unstructured / LangChain DocumentLoader（PDF/Word/网页/字幕） |
| HTTP 框架 | FastAPI + Uvicorn |
| CLI 框架 | argparse |
| 配置管理 | Pydantic Settings + python-dotenv |
| 可观测性 | LangSmith + 自建 Tracer/Metrics |
