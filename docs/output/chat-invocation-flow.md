# 用户聊天 → Agent 响应全链路调用流程

> 分析日期：2026-05-30
> 分析范围：前端 index.html → 后端 /chat API → Orchestrator → Skill → 模型调用 → 响应返回

---

## 一、前端发起请求（frontend/index.html）

### 代码位置
`frontend/index.html` 第 1196~1244 行

### 流程

```javascript
async function sendMessage() {
    const text = input.value.trim();
    const model = document.getElementById('model').value || null;

    // 1. 立即在前端渲染用户消息
    appendMessage('user', text);
    setLoading(true);

    // 2. 调用 /chat 接口
    const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
            prompt: text,
            model: model,                 // 用户选择的模型（可选）
            session_id: currentSessionId, // 复用会话（可选）
            chat_history: history,        // 最近 20 轮历史
        }),
    });

    const data = await res.json();
    if (res.ok) {
        // 3. 渲染 Agent 响应，附带模型名称
        appendMessage('agent', data.output, data.model);
        history.push(['human', text]);
        history.push(['ai', data.output]);
        currentSessionId = data.session_id || currentSessionId;
    }
}
```

### 关键说明
- **模型选择**：用户可从下拉框选择模型，未选择时后端使用默认模型（`settings.default_model`）
- **会话保持**：`session_id` 在首次对话时由后端生成，后续轮次复用
- **历史截断**：前端只保留最近 20 轮，防止上下文过长
- **appendMessage 增强**：Agent 消息区域现在显示模型标签（如 `Agent  DeepSeek V4 Pro`）和复制按钮

---

## 二、后端 API 入口（src/comedy_agent/api/server.py）

### 2.1 应用启动：lifespan 初始化

`src/comedy_agent/api/server.py` 第 318~377 行

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 加载外部 Prompt 模板
    PromptManager().load_from_directory()

    # 2. 初始化统一记忆（失败不阻断）
    try:
        state.memory = UnifiedMemory()
    except Exception as e:
        state.memory = None

    # 3. 初始化知识库检索器
    vector_store = VectorStore(collection_name="comedy_knowledge", ...)
    retriever = ComedyRetriever(vector_store=vector_store)

    # 4. 初始化 Orchestrator 并注册所有 Skill
    state.orch = AgentOrchestrator(memory=state.memory, retriever=retriever)
    state.orch.register_skill(StandupSkill())
    state.orch.register_skill(CrosstalkSkill())
    state.orch.register_skill(SketchSkill())
    state.orch.register_skill(SitcomSkill())
    state.orch.register_skill(ManzaiSkill())
    state.orch.register_skill(JapaneseSketchSkill())
    state.orch.register_skill(JokeAnalyzerSkill())
    state.orch.register_skill(ScriptEvaluatorSkill())

    # 5. 加载外部插件 Skill
    for plugin in load_plugin_skills():
        state.orch.register_skill(plugin)
```

### 2.2 `/chat` 接口处理流程

`src/comedy_agent/api/server.py` 第 543~619 行

```python
@app.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(request: ChatRequest, user_id: str = Depends(get_current_user)):
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")

    # 1. 运行时模型切换
    if request.model:
        state.orch.set_model(request.model)

    # 2. 生成/复用 session_id
    session_id = request.session_id or uuid.uuid4().hex[:16]

    with tracer.span("api.chat", ...) as span:
        # 3. 调用 Orchestrator
        result = state.orch.run(
            request.prompt,
            chat_history=request.chat_history,
            user_id=user_id,
        )

        # 4. 序列化消息链
        messages = []
        for msg in result.get("messages", []):
            messages.append({
                "role": getattr(msg, "type", "unknown"),
                "content": str(getattr(msg, "content", "")),
            })

        # 5. 保存会话到记忆系统（失败不影响主流程）
        if state.memory is not None:
            try:
                state.memory.save_conversation(
                    user_id=user_id,
                    session_id=session_id,
                    messages=messages,
                    summary=result["output"][:80],
                )
            except Exception:
                pass  # 静默忽略

        # 6. 自动提取用户偏好（深度≥3 且字数>200 时触发）
        try:
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)
            if len(messages) >= 3 and total_chars > 200:
                new_prefs = extract_preferences(messages)
                merge_preferences(user_id, new_prefs, memory=state.memory)
        except Exception:
            pass  # 静默忽略

        # 7. 构造响应（含实际使用的模型名称）
        orch_model = getattr(state.orch, 'model_name', None) if state.orch else None
        model_used = request.model or (orch_model if isinstance(orch_model, str) else None) or settings.default_model
        return ChatResponse(
            output=result["output"],
            session_id=session_id,
            model=model_used,
            messages=messages,
        )
```

### 关键分支与异常处理

| 环节 | 正常流程 | 异常处理 |
|------|---------|---------|
| 服务就绪检查 | `state.orch` 已初始化 | 返回 HTTP 503 |
| 模型切换 | `orch.set_model()` 同步更新所有 Skill | — |
| 记忆保存 | 写入 SQLite + 更新会话摘要 | 静默忽略，不影响响应 |
| 偏好提取 | LLM 分析对话提取键值对 | 静默忽略 |
| 顶层异常 | — | 捕获为 HTTP 500 |

---

## 三、Orchestrator 路由决策（src/comedy_agent/agent/orchestrator.py）

### 3.1 入口：`run()` 方法的双分支

`src/comedy_agent/agent/orchestrator.py`

```python
def run(self, user_input: str, chat_history=None, user_id=None):
    # ===== 分支 A：用户显式指定 Skill =====
    skill_name, actual_request = self._parse_skill_directive(user_input)
    # 正则匹配："使用 xxx 技能" / "用 xxx 技能"
    if skill_name:
        skill = self._find_skill(skill_name)
        if skill is not None:
            return self._invoke_directive_skill(skill, actual_request, user_id=user_id)
        logger.warning("指定 Skill '%s' 未找到，回退到 Agent 路由", skill_name)

    # ===== 分支 B：Agent 自动路由 =====
    agent = self._build_agent()
    system_prompt = self._build_system_prompt(user_input, user_id)

    messages = [("system", system_prompt)]
    if chat_history:
        for role, content in chat_history:
            messages.append((role, content))
    messages.append(("human", user_input))

    result = agent.invoke({"messages": messages})
    # 提取最后一条 AIMessage 作为输出
    output = ""
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage):
            output = str(msg.content)
            break

    return {"output": output, "messages": result.get("messages", [])}
```

### 分支对比

| 维度 | 分支 A：Skill 指令直接路由 | 分支 B：Agent 自动路由 |
|------|--------------------------|----------------------|
| 触发条件 | 用户输入含 `"使用 xxx 技能..."` | 未匹配到技能指令 |
| 解析方式 | LLM 提取 JSON 参数后直接调用 Skill | Agent 内部决策调用哪个 Tool |
| System Prompt | 仅 Skill 内部自行构建 | Orchestrator 统一构建（含记忆+知识库） |
| 记忆注入 | Skill 内部通过 `retriever` 自行检索 | Orchestrator 统一注入 |
| 典型场景 | "使用 standup 技能写一段关于加班的脱口秀" | "帮我写个搞笑段子" |

---

## 四、System Prompt 构建（记忆 + 知识库注入）

### 4.1 `_build_system_prompt` 流程

```python
def _build_system_prompt(self, user_input: str, user_id: str | None = None) -> str:
    parts: list[str] = [self.system_prompt]

    # 1. 注入用户记忆（偏好 + 近期会话 + 近期作品）
    if self.memory and user_id:
        memory_text = self.memory.build_context_text(user_id)
        if memory_text:
            parts.append(f"【关于用户】\n{memory_text}\n【关于用户结束】")

    # 2. 注入知识库（个人库优先 + 默认库）
    all_docs: list[Any] = []
    if user_id:
        user_docs = self._retrieve_user_knowledge(user_input, user_id, top_k=3)
        all_docs.extend(user_docs)

    if self.retriever is not None:
        try:
            default_docs = self.retriever.retrieve(user_input, top_k=5)
            all_docs.extend(default_docs)
        except Exception:
            pass

    # 去重并格式化
    if all_docs:
        seen: set[str] = set()
        unique_docs = []
        for doc in all_docs:
            key = doc.metadata.get("doc_id") or doc.page_content
            if key and key not in seen:
                seen.add(key)
                unique_docs.append(doc)
        parts.append(knowledge_text)

    return "\n\n".join(parts)
```

### 4.2 记忆系统 Token 预算控制

`src/comedy_agent/memory/unified.py`

```python
def build_context_text(self, user_id: str, max_tokens: int = 800, ...) -> str:
    items = []

    # 优先级 1：用户偏好
    if ctx.preferences:
        items.append((1, "【用户偏好】\n..."))

    # 优先级 2：近期会话摘要
    if ctx.recent_conversations:
        items.append((2, "【近期会话】\n..."))

    # 优先级 3：近期作品
    if ctx.recent_scripts:
        items.append((3, "【近期作品】\n..."))

    # Token 预算控制：按优先级逐段截断
    result_parts = []
    current_tokens = 0
    for priority, part in sorted(items):
        if current_tokens + estimate(part) <= max_tokens:
            result_parts.append(part)
            current_tokens += estimate(part)
        else:
            # 段内逐行截断
            ...
    return "\n\n".join(result_parts)
```

### 关键说明
- **优先级**：用户偏好 > 近期会话 > 近期作品
- **Token 估算**：中文 ~1.5 tokens/字，英文 ~0.25 tokens/字符
- **超出预算**：从低优先级内容开始截断，保留高优先级信息

---

## 五、Skill 执行示例：StandupSkill

### 5.1 直接路由调用链

```
_invoke_directive_skill()
    ├── _extract_skill_args()       # LLM 将自然语言解析为 JSON 参数
    │       └── self.llm.invoke()   # 调用 Orchestrator 的 LLM
    └── skill.invoke(args)          # 调用 Skill._run()
            └── StandupSkill._run()
```

### 5.2 `StandupSkill._run()` 完整流程

`src/comedy_agent/skills/standup.py`

```python
def _run(self, topic, style="日常观察", duration=3, audience="通用",
         density="标准", perspective_count=2, user_id=None, debug=False):
    # 1. 检索知识库（支持 kind/style 过滤）
    docs = self._retrieve_knowledge(topic, user_id, kind="standup", style=style)
    knowledge_text = self._format_knowledge(docs)

    # 2. 构建 System Prompt
    system_prompt = self.SYSTEM_PROMPT          # 从 standup-template.md 加载
    if debug:
        system_prompt += "\n\n" + _DEBUG_NOTE   # 输出分析过程
    else:
        system_prompt += "\n\n" + _OUTPUT_CONSTRAINT  # 强制只输出正文
    if knowledge_text:
        system_prompt += f"\n\n{knowledge_text}"

    # 3. 构建 Prompt 链
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", self._build_user_prompt(...)),
    ])

    # 4. 获取模型（带自动降级）
    llm = ModelFactory.get_model_with_fallback(
        name=self.model_name, task_type=self.task_type
    )

    # 5. 执行链式调用
    chain = prompt | llm
    result = chain.invoke({})
    return str(result.content)
```

### 关键分支

| 模式 | 触发条件 | 输出内容 |
|------|---------|---------|
| 正常模式 | `debug=False`（默认） | 只输出段子正文，严禁分析/标签/标题 |
| Debug 模式 | `debug=True` | 输出完整创作分析过程 + 正文 |

### 5.3 知识库检索（基类实现）

`src/comedy_agent/skills/base.py`

```python
def _retrieve_knowledge(self, query, user_id=None, top_k=5, kind=None, style=None):
    filter_dict = {}
    if kind:  filter_dict["kind"] = kind
    if style: filter_dict["style"] = style

    all_docs = []

    # 个人知识库（失败静默）
    if user_id:
        try:
            store = self._get_user_vector_store(user_id)
            user_docs = store.search(query, top_k=3, filter_dict=filter_dict)
            all_docs.extend(user_docs)
        except Exception:
            pass

    # 默认知识库（失败静默）
    if self.retriever is not None:
        try:
            default_docs = self.retriever.retrieve(query, top_k=top_k, filter_dict=filter_dict)
            all_docs.extend(default_docs)
        except Exception:
            pass

    # 去重，最多返回 6 条
    return unique_docs[:6]
```

---

## 六、模型调用（src/comedy_agent/models/factory.py）

### 6.1 注册表初始化

```python
class ModelFactory:
    _llm_registry: dict[str, Callable[..., BaseChatModel]] = {}

    @classmethod
    def _build_default_llm_registry(cls):
        # OpenAI (gpt-4o, gpt-4o-mini)
        # Anthropic (claude-3-5-sonnet, claude-3-opus)
        # 通义千问 (qwen-max, qwen-plus, qwen-turbo)
        # Moonshot/Kimi (OpenAI 兼容接口)
        # Ollama 本地模型 (llama3, qwen2.5)
        # 万界数据/WJark (中转站，覆盖 GLM/DeepSeek/Qwen/Kimi/MiniMax 等 20+ 模型)
```

### 6.2 `get_model()` 核心逻辑

```python
_TASK_TYPE_MAP = {
    "creative": "creative_model",      # 创作类任务
    "analytical": "analytical_model",  # 分析类任务
    "fast": "fast_model",              # 快速响应任务
}

def get_model(cls, name=None, task_type=None, **kwargs):
    cls._ensure_initialized()

    # 按 task_type 解析模型名
    if name is None and task_type is not None:
        attr = cls._TASK_TYPE_MAP.get(task_type)
        name = getattr(settings, attr, settings.default_model)

    name = name or settings.default_model

    # 注册表命中
    if name in cls._llm_registry:
        return cls._llm_registry[name](**kwargs)

    # Ollama 动态解析
    if name.startswith("ollama-"):
        return ChatOllama(model=name.replace("ollama-", ""), **kwargs)

    raise ValueError(f"未知模型 '{name}'")
```

### 6.3 自动降级：`get_model_with_fallback()`

```python
def get_model_with_fallback(cls, name=None, task_type=None, **kwargs):
    primary = cls.get_model(name=name, task_type=task_type, **kwargs)

    # 从配置解析备用模型链
    fallback_names = []
    if task_type:
        attr = f"{task_type}_fallback_models"
        fallback_str = getattr(settings, attr, "")
        if fallback_str:
            fallback_names = [n.strip() for n in fallback_str.split(",")]

    fallbacks = []
    for fb_name in fallback_names:
        try:
            fallbacks.append(cls.get_model(name=fb_name, **kwargs))
        except Exception:
            pass

    return RunnableWithFallbacks(
        runnable=primary,
        fallbacks=fallbacks,
        exceptions_to_handle=(Exception,),
    )
```

---

## 七、RAG 混合检索（src/comedy_agent/rag/retriever.py）

### 7.1 `retrieve()` 三阶段流程

```python
def retrieve(self, query: str, top_k: int = 5, filter_dict=None):
    # 1. 尝试缓存命中
    if self.cache is not None:
        cached = self.cache.get_json(cache_key)
        if cached is not None:
            return cached

    # 2. 向量检索召回
    vec_results = self.vector_store.search(query, top_k=vec_k, filter_dict=filter_dict)

    # 3. 多向量检索召回（如果启用）
    if self.multi_vector_store is not None:
        mv_results = self.multi_vector_store.search(query, top_k=vec_k)
        vec_results = self._merge_results(vec_results, mv_results)

    # 4. BM25 关键词检索召回
    bm25_results = self._bm25_search(query, top_k=bm25_k)

    # 5. 合并去重
    merged = self._merge_results(vec_results, bm25_results)

    # 6. Cross-Encoder 重排序
    reranked = self._rerank(query, merged, top_k=top_k)

    # 7. 写入缓存
    if self.cache is not None:
        self.cache.set_json(cache_key, serializable, ttl=self.cache_ttl)

    return reranked
```

### 检索三阶段

| 阶段 | 方法 | 作用 | 降级策略 |
|------|------|------|---------|
| 召回 | 向量检索 + BM25 + 多向量 | 最大化召回率 | 各阶段独立，失败返回空列表 |
| 去重 | `_merge_results` | 按 `doc_id` / `content` 去重 | — |
| 排序 | Cross-Encoder 重排序 | 精细语义相关性排序 | 未安装时直接截断 `[:top_k]` |

---

## 八、完整调用链路图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户浏览器                                        │
│  ┌─────────────┐     输入消息 + 选择模型                                       │
│  │ frontend/   │ ─────────────────────────► POST /chat                         │
│  │ index.html  │ ◄───────────────────────── ChatResponse                       │
│  │             │         (output, model, session_id)                          │
│  └─────────────┘                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FastAPI 服务端                                       │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ lifespan 启动（一次性）                                                │ │
│  │ ├── UnifiedMemory() ──► SQLite (data/memory.db)                        │ │
│  │ ├── VectorStore() ──► ChromaDB (chroma_data/)                          │ │
│  │ ├── ComedyRetriever(VectorStore)                                       │ │
│  │ └── AgentOrchestrator(memory, retriever)                               │ │
│  │     └── 注册 8 个内置 Skill + 插件 Skill                               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ /chat 接口处理                                                         │ │
│  │ 1. orch.set_model(request.model)         [可选运行时切换]              │ │
│  │ 2. orch.run(user_input, chat_history, user_id)                         │ │
│  │ 3. 序列化 messages                                                     │ │
│  │ 4. memory.save_conversation()            [失败静默忽略]                │ │
│  │ 5. extract_preferences()                 [深度≥3 时触发]               │ │
│  │ 6. 返回 ChatResponse(output, session_id, model, messages)              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AgentOrchestrator 路由层                               │
│                                                                              │
│  ┌──────────────────────────┐    ┌──────────────────────────────────────┐   │
│  │ 分支 A：Skill 指令直接路由  │    │ 分支 B：Agent 自动路由                 │   │
│  │                          │    │                                      │   │
│  │ 1. _parse_skill_directive│    │ 1. _build_system_prompt()            │   │
│  │    "使用 standup 技能..." │    │    ├── memory.build_context_text()   │   │
│  │                          │    │    └── retriever.retrieve()          │   │
│  │ 2. _extract_skill_args() │    │ 2. _build_agent()                    │   │
│  │    LLM 解析 JSON 参数     │    │    └── create_agent(LangGraph)       │   │
│  │                          │    │ 3. agent.invoke({"messages": [...]}) │   │
│  │ 3. skill.invoke(args)    │    │    └── Agent 内部决策调用 Tool       │   │
│  │    └── StandupSkill._run()│    │                                      │   │
│  └──────────────────────────┘    └──────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Skill 执行层                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ StandupSkill._run()（典型 Skill）                                      │ │
│  │ 1. _retrieve_knowledge(topic, user_id, kind="standup", style=style)   │ │
│  │    ├── 个人知识库 (ChromaDB: user_knowledge_{user_id})                 │ │
│  │    └── 默认知识库 (ChromaDB: comedy_knowledge)                         │ │
│  │ 2. 构建 System Prompt                                                  │ │
│  │    ├── 模板 (standup-template.md)                                      │ │
│  │    ├── 约束 (_OUTPUT_CONSTRAINT / _DEBUG_NOTE)                         │ │
│  │    └── 知识库结果                                                     │ │
│  │ 3. ModelFactory.get_model_with_fallback()                              │ │
│  │ 4. chain.invoke({}) ──► LLM 生成                                      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              模型层                                            │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ ModelFactory.get_model()                                               │ │
│  │ ├── 注册表命中（OpenAI/Anthropic/通义/Ollama/Kimi/WJark）              │ │
│  │ ├── Ollama 动态解析（ollama-{model_id}）                               │ │
│  │ └── 未知模型 → ValueError                                              │ │
│  │                                                                        │ │
│  │ RunnableWithFallbacks（可选）                                          │ │
│  │ └── 主模型异常时自动切换到备用模型                                      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 九、异常处理总览

| 层级 | 场景 | 处理策略 |
|------|------|---------|
| **lifespan 初始化** | 记忆/检索器初始化失败 | 记录 warning，不阻断服务启动 |
| **lifespan 初始化** | 模型配置错误 | `state.orch = None`，后续请求返回 503 |
| **API 层** | 任何未捕获异常 | 转换为 HTTP 500 |
| **API 层** | 记忆保存/偏好提取失败 | 静默忽略，不影响主响应 |
| **Orchestrator** | Skill 指令未找到对应 Skill | 回退到 Agent 自动路由 |
| **Orchestrator** | 知识库检索失败 | 静默跳过，System Prompt 中不注入知识 |
| **Skill** | 知识库检索失败 | 静默忽略，继续执行创作流程 |
| **Skill** | LLM 调用失败 | `RunnableWithFallbacks` 自动降级到备用模型 |
| **Retriever** | BM25 未安装 | 仅使用向量检索 |
| **Retriever** | Cross-Encoder 未安装 | 召回后直接去重截断，不重排序 |
| **Retriever** | 缓存失效/未命中 | 不影响检索正确性，仅影响性能 |

---

## 十、关键配置项

| 配置 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| 默认模型 | `.env` → `DEFAULT_MODEL` | `gpt-4o` | 未指定模型时使用 |
| 创作模型 | `.env` → `CREATIVE_MODEL` | — | `task_type="creative"` 时优先使用 |
| 分析模型 | `.env` → `ANALYTICAL_MODEL` | — | `task_type="analytical"` 时优先使用 |
| 备用模型链 | `.env` → `*_FALLBACK_MODELS` | — | 逗号分隔，主模型失败时依次尝试 |
| 向量库路径 | `.env` → `VECTOR_DB_PATH` | `./chroma_data` | ChromaDB 持久化目录 |
| 记忆数据库 | `.env` → `MEMORY_DB_PATH` | `./data/memory.db` | SQLite 数据库文件 |
| 会话 TTL | `SQLMemoryStore.save_conversation` | 24 小时 | 短期记忆自动过期 |
| 记忆 Token 预算 | `build_context_text.max_tokens` | 800 | 注入 System Prompt 的记忆上限 |
| Embedding 模型 | `.env` → `EMBEDDING_MODEL` | `hf-local` | `all-MiniLM-L6-v2`，384 维 |
| Cross-Encoder | `ComedyRetriever.__init__` | `ms-marco-MiniLM-L-6-v2` | 重排序模型 |
