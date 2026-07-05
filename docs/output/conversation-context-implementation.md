# 喜剧 Agent 对话上下文管理实现说明

> 文档范围：`src/comedy_agent` 目录  
> 核心问题：用户多轮对话的上下文是如何维护、传递、持久化与截断的。

---

## 一、总体设计

`src/comedy_agent` 的对话上下文管理由三层机制配合实现：

1. **运行时状态层**：`ComedyState`（`state/schema.py`）维护当前会话的完整状态，核心字段是 `messages`（LangChain 消息链）。
2. **图编排层**：LangGraph `StateGraph` 通过 `add_messages` reducer 自动合并各节点返回的新消息，实现上下文累积。
3. **持久化层**：
   - **Checkpoint**：`MemorySaver` 按 `thread_id = session_id` 保存图运行状态，供下一轮恢复。
   - **数据库**：`SQLMemoryStore` 把完整对话记录写入 SQLite，支持跨会话查询。

---

## 二、核心状态：`ComedyState`

文件：`src/comedy_agent/state/schema.py`

```python
class ComedyState(BaseModel):
    phase: Literal[...] = "idle"
    session_id: str = ""
    user_id: str | None = None
    user_input: str = ""
    output: str = ""
    messages: Annotated[list[AnyMessage], add_messages] = Field(
        default_factory=list, description="LangChain 消息链"
    )
    chat_history: list[tuple[str, str]] | None = Field(
        default=None, description="前端传入的历史消息 [(role, content), ...]"
    )
    ...
```

关键字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `messages` | `list[AnyMessage]` | 运行时消息链，元素为 `HumanMessage` / `AIMessage` / `SystemMessage`。使用 `Annotated[..., add_messages]` 声明 reducer，节点返回的新消息会被**追加合并**。 |
| `chat_history` | `list[tuple[str, str]]` | 前端传来的简化历史，格式为 `[(role, content), ...]`，主要在 `chat_node` 与旧版 Orchestrator 中使用。 |
| `session_id` | `str` | 会话标识，对应 LangGraph 的 `thread_id`，用于 checkpoint 恢复。 |
| `user_id` | `str \| None` | 用户标识，用于数据库持久化与权限控制。 |

---

## 三、两条主要链路

项目目前同时存在两条对话上下文链路：

| 链路 | 入口 | 上下文维持方式 |
|------|------|----------------|
| **v4 LangGraph** | `/chat`、`/pro/chat-v4` | 通过 `session_id` 恢复 LangGraph checkpoint，`messages` 在图运行中自动累积。 |
| **旧版 Orchestrator** | `/salt`、`/speed` 等 | 每次请求由前端传入完整 `chat_history`，Orchestrator 自行拼接 system prompt + history + user input。 |

---

## 四、v4 LangGraph 详细流程

以专业版 B 接口 `/pro/chat-v4` 为例，文件位置：`src/comedy_agent/api/routers/pro_v4.py`。

### 4.1 接收请求并确定会话标识

```python
session_id = request.session_id or uuid.uuid4().hex[:16]
config = {"configurable": {"thread_id": session_id}}
```

- 若前端未传 `session_id`，则生成新的 16 位 hex 字符串。
- 若已传，则复用，保证多轮对话上下文连续。

### 4.2 从 checkpoint 恢复历史状态

```python
current = state.graph.get_state(config)
prev_values = (current.values or {}) if current else {}
```

通过 `thread_id` 读取上一轮保存的完整状态，包括 `messages`、`analysis`、`plan`、`sections`、`feedback` 等。

### 4.3 构造本轮初始状态

```python
merged_state = {
    **prev_values,
    "phase": "idle",
    "user_input": request.message,
    "model": request.model,
    "messages": [HumanMessage(content=request.message)],
    "session_id": session_id,
    "user_id": user_id,
    ...
}
raw_result = await state.graph.ainvoke(
    ComedyState(**merged_state),
    config=config,
)
```

注意：`messages` 字段只放入本轮新的 `HumanMessage`，LangGraph 的 `add_messages` reducer 会自动将其与 `prev_values` 中的历史 `messages` 合并。

### 4.4 Supervisor 路由

文件：`src/comedy_agent/agents/supervisor.py`

根据 `phase` 决定进入哪个 Worker 节点：

- `idle` → `intent_classifier`
- 意图为 `chat` → `chatting` → `chat_node`
- 意图为 `writing` → `filling_slots` → `analyzing` → `planning` → ... → `writing`

### 4.5 各节点对上下文的使用方式

#### 4.5.1 `chat_node`（闲聊分支）

文件：`src/comedy_agent/nodes/chat_node.py`

```python
messages = [SystemMessage(content=DEFAULT_SYSTEM_PROMPT)]

if state.chat_history:
    for role, content in state.chat_history:
        if role == "system": messages.append(SystemMessage(content=content))
        elif role == "ai": messages.append(AIMessage(content=content))
        else: messages.append(HumanMessage(content=content))

if state.user_input:
    messages.append(HumanMessage(content=state.user_input))

response = llm.invoke(messages)
```

这是最传统的拼接方式：`[SystemMessage] + chat_history + [HumanMessage]`，直接传给 LLM。

#### 4.5.2 创作类 Agent（上下文分析、计划、引导）

这些节点不把 `state.messages` 直接传给 LLM，而是将其格式化为**对话历史文本**后嵌入 Prompt。

以 `ContextAnalyzerAgent` 为例，文件：`src/comedy_agent/agents/context_analyzer.py`：

```python
def _format_history(messages, max_turns=8):
    if not messages:
        return "（暂无）"
    recent = messages[-max_turns * 2:]  # 每轮包含 human + ai
    lines = []
    for m in recent:
        if getattr(m, "type", None) == "human":
            lines.append(f"用户：{m.content}")
        elif getattr(m, "type", None) == "ai":
            lines.append(f"助手：{m.content}")
    return "\n".join(lines)
```

`PlannerAgent` 与 `GuideAgent` 类似，分别取最近 8 轮与最近 10 条消息。

#### 4.5.3 `WriterAgent`（写作分支）

`WriterAgent` 不直接消费消息链，而是通过 `graph/state_modifier.py` 的 `build_prompts()` 将 `plan`、`sections`、`feedback`、`analysis` 等状态字段拼成 system/user prompt。

### 4.6 LangGraph 自动合并状态

每个节点返回更新字典，例如：

```python
return {
    "output": output,
    "messages": output_messages,  # 包含 System + history + Human + AIMessage
    "phase": "complete",
}
```

LangGraph 通过 `add_messages` reducer 将 `messages` 追加到全局状态，实现上下文自动累积。

### 4.7 AI 回复回写 checkpoint

文件：`src/comedy_agent/api/routers/pro_v4.py:562-568`

```python
state.graph.update_state(
    config,
    {"messages": [AIMessage(content=response.content)]},
)
```

在返回前端之前，显式把本轮 AI 回复追加到 checkpoint，确保下一轮 `ContextAnalyzer` / `Planner` 能看到完整对话历史。

### 4.8 多轮循环

前端在下一轮请求中继续携带同一 `session_id`，重复步骤 4.2-4.7，实现上下文延续。

---

## 五、旧版 Orchestrator 链路

文件：`src/comedy_agent/agent/orchestrator.py:594-680`

```python
def run(self, user_input, chat_history=None, user_id=None):
    system_prompt = self._build_system_prompt(user_input, user_id)
    messages = [("system", system_prompt)]

    if chat_history:
        for role, content in chat_history:
            messages.append((role, content))

    messages.append(("human", user_input))
    result = agent.invoke({"messages": messages})
```

特点：

- 无 LangGraph checkpoint，完全依赖前端每次传入完整 `chat_history`。
- 先注入系统提示 + 知识库（个人库 / 默认库 / 共享库）。
- 再按顺序追加历史消息和当前用户输入。
- 最后调用 LangChain Agent。

---

## 六、持久化机制

### 6.1 Checkpoint 持久化（运行时）

文件：`src/comedy_agent/checkpoints/memory.py:23-38`

```python
class MemorySaverFactory:
    _instance: MemorySaver | None = None

    @classmethod
    def get(cls) -> MemorySaver:
        if cls._instance is None:
            cls._instance = MemorySaver(serde=_serde)
        return cls._instance
```

当前使用的是**内存版 `MemorySaver`**，按 `thread_id = session_id` 保存图运行状态。

⚠️ **限制**：服务器重启后内存 checkpoint 会丢失，但 SQLite 中的 `user_conversations` 记录仍然保留。

### 6.2 数据库持久化（跨会话）

数据库表定义：`src/comedy_agent/memory/schema.py:197-222`

```python
class UserConversation(Base):
    __tablename__ = "user_conversations"
    session_id = mapped_column(String(64), primary_key=True)
    user_id = mapped_column(ForeignKey(...), index=True, nullable=False)
    messages = mapped_column(JSON, default=list, nullable=False)
    summary = mapped_column(Text, nullable=True)
    source = mapped_column(String(16), default="chat")
    expires_at = mapped_column(DateTime, nullable=True)
```

SQLite 实现：`src/comedy_agent/memory/medium_term.py:342-398`

- 默认数据库文件：`./data/memory.db`（由 `core/config.py` 中的 `memory_db_path` 配置）。
- 会话记录 24 小时过期（`expires_at = now + timedelta(hours=24)`）。

API 层保存调用：`src/comedy_agent/api/server.py:669-680`

```python
if state.memory is not None:
    state.memory.save_conversation(
        user_id=user_id,
        session_id=session_id,
        messages=messages,
        summary=result.output[:80] if result.output else None,
        source=request.source,
    )
```

同时提供 REST 接口管理会话：

- `GET /conversations`：列出会话
- `GET /conversations/{session_id}`：读取单条会话
- `DELETE /conversations/{session_id}`：删除会话

---

## 七、上下文长度与截断策略

### 7.1 按轮数截断

| Agent | 截断策略 |
|-------|----------|
| `ContextAnalyzerAgent` | `_format_history(..., max_turns=8)`，只取最近 8 轮 |
| `PlannerAgent` | 同上，最近 8 轮 |
| `GuideAgent` | 取最近 10 条消息 |

### 7.2 Token 预算控制

- **RAG 上下文注入**：`src/comedy_agent/rag/context_injector.py:167-208`
  - 函数：`_truncate_to_budget()`
  - 默认 `max_context_tokens=2000`
  - 按段落/条目截断，优先保留前面的检索结果。

- **记忆上下文**：`src/comedy_agent/memory/unified.py:371-475`
  - 函数：`build_context_text()`
  - 默认 `max_tokens=800`
  - 按段/条截断，优先级：用户偏好 > 近期会话摘要 > 近期作品。
  - ⚠️ 该函数目前尚未被主流程调用，属于预留能力。

### 7.3 摘要机制

数据库有 `summary` 字段，但当前仅在保存会话时用 `result.output[:80]` 存储一个简单摘要，**尚未实现基于 LLM 的长对话自动摘要压缩机制**。

---

## 八、关键文件索引

| 文件路径 | 作用 |
|----------|------|
| `src/comedy_agent/state/schema.py` | `ComedyState` 全局状态定义 |
| `src/comedy_agent/checkpoints/memory.py` | LangGraph `MemorySaver` 工厂 |
| `src/comedy_agent/graph/supervisor_graph.py` | Supervisor 星型图构建 |
| `src/comedy_agent/graph/state_modifier.py` | 动态 Prompt 四层组装 |
| `src/comedy_agent/nodes/chat_node.py` | 闲聊节点，直接拼接消息链 |
| `src/comedy_agent/agents/context_analyzer.py` | 上下文分析，取最近 8 轮 |
| `src/comedy_agent/agents/planner.py` | 计划生成，取最近 8 轮 |
| `src/comedy_agent/agents/guide.py` | 引导回复，取最近 10 条 |
| `src/comedy_agent/agents/writer.py` | 写作节点，调用 `build_prompts` |
| `src/comedy_agent/memory/unified.py` | 统一记忆入口 |
| `src/comedy_agent/memory/medium_term.py` | SQLite 记忆存储实现 |
| `src/comedy_agent/memory/schema.py` | SQLAlchemy ORM 表定义 |
| `src/comedy_agent/api/routers/pro_v4.py` | 专业版 B `/pro/chat-v4` 入口 |
| `src/comedy_agent/api/server.py` | `/chat` 入口 + 会话 CRUD |
| `src/comedy_agent/agent/orchestrator.py` | 旧版编排器，依赖 `chat_history` |
| `src/comedy_agent/rag/context_injector.py` | RAG 上下文注入与截断 |

---

## 九、结论

`src/comedy_agent` 的用户对话上下文管理可概括为：

> **运行时以 `ComedyState.messages` 为中心，LangGraph 通过 `add_messages` reducer 自动累积消息；以 `session_id` 作为 `thread_id` 通过 `MemorySaver` checkpoint 恢复历史状态；同时由 `SQLMemoryStore` 将完整对话持久化到 SQLite。闲聊节点直接拼接 `[System] + history + [Human]`；创作类节点将历史格式化为文本嵌入 Prompt，并只取最近 8-10 轮控制长度。**

当前存在的可改进点：

1. Checkpoint 为内存版，服务重启后运行时会话状态丢失。
2. `UnifiedMemory.build_context_text()` 尚未接入主链路，用户长期记忆未充分利用。
3. 长对话尚无自动 LLM 摘要压缩机制，仅靠固定轮数截断。
