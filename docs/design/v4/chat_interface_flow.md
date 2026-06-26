# v4 `/chat` 与 `/pro/chat-v4` 接口流程说明

## 1. 总体架构

`/chat` 和 `/pro/chat-v4` 共用同一套 v4 Supervisor StateGraph，核心文件：

- `src/comedy_agent/graph/supervisor_graph.py` —— 星型拓扑图定义
- `src/comedy_agent/agents/supervisor.py` —— 纯代码路由，根据 `state.phase` 派发 Worker
- `src/comedy_agent/state/schema.py` —— 全局状态 Schema

**Supervisor 的角色**：它只负责根据 `state.phase` 决定下一步去哪个 Worker，不生成内容。所有内容生成由专门的 Worker Agent 完成。

---

## 2. `/chat` 单次请求流程

```text
POST /chat
  └─ state.graph.ainvoke(ComedyState(user_input=..., model=..., chat_history=...))
       └─ START → supervisor
            └─ 按 phase 路由到不同 Worker
```

### 2.1 主要阶段与路由

| phase | Supervisor 路由 | Worker 节点 | 职责 |
|-------|-----------------|-------------|------|
| `idle` | `intent_classifier` | `entry_node` | 优先识别 `@话题/态度/偏见/情绪`，否则调用 LLM 判断意图 |
| `filling_slots` | `slot_filler` | `slot_filler_node` | 提取 `@` 槽位 |
| `slot_checking` | `slot_checker` | `slot_checker_node` | 检查 4 维度槽位是否填满，缺失则转 `consulting` |
| `consulting` | `guide` | `guide_node` | 生成自然语言回复 + A/B/C 可选项 |
| `analyzing` | `context_analyzer` | `analyze_node` | 四维度分析（话题/态度/偏见/情绪） |
| `planning` | `planner` | `plan_node` | 生成 Todo List + 段落 Outline |
| `plan_review` | `plan_review` | `plan_review_node` | `interrupt()` 暂停，等待用户确认/修改/重新规划 |
| `writing` | `writer` | `write_node` | 按大纲逐段撰写内容 |
| `reviewing` | `reviewer` | `review_node` | 审核当前段落质量 |
| `human_review` | `human` | `human_node` | `interrupt()` 暂停，等待用户反馈 |
| `finalizing` | `finalize` | `finalize_node` | 拼接所有段落，输出最终文本 |
| `complete` | `__end__` | — | 结束本次图执行 |

### 2.2 Human-in-the-Loop 说明

有两处会触发 `interrupt()` 暂停：

1. **计划审阅（`plan_review`）**：Planner 生成计划后暂停，用户反馈后决定进入写作或重新规划。
2. **段落审阅（`human_review`）**：Writer 写完一段后暂停，用户反馈后决定通过/修改/重写。

前端恢复方式：再次调用接口并传入用户反馈：

- `/chat`：传 `feedback` 字段
- `/pro/chat-v4`：后端自动检测 `phase`，使用 `Command(resume=message)` 恢复

---

## 3. `/chat` 响应格式

```ts
interface ChatResponse {
  output: string;                       // Agent 输出文本
  session_id: string | null;            // 会话 ID
  model: string | null;                 // 实际使用的模型
  status: "complete" | "waiting_feedback";
  messages: Array<{ role: string; content: string }>;
  suggestion: SuggestionResponse | null; // 改进建议（可选）
}
```

- **`status=complete`**：流程正常结束，`output` 为最终返回文本。
- **`status=waiting_feedback`**：图执行触发了 `interrupt()`，前端需要保存 `session_id`，并在下一次请求时传入 `feedback` 恢复执行。

> **当前限制**：`/chat` 对 `plan_review` 的处理不够完整，它只读取 `section_text`；在计划审阅时会返回空 `output`。建议需要完整中间状态的场景使用 `/pro/chat-v4`。

---

## 4. `/pro/chat-v4` 响应格式

专业版 B（`frontend/pro-b.html`）使用此接口，能完整表达中间状态：

```ts
interface ProChatV4Response {
  session_id: string;
  type: "guide" | "skill_output" | "final_script" | "error";
  content: string;                      // 显示给用户的文本
  workflow_state: string;               // 当前工作流状态
  current_role: string | null;          // 当前发言角色
  next_role: string | null;             // 下一个该发言的角色
  next_actions: Array<{
    label: string;
    action: string;
    value: string;
  }> | null;                             // A/B/C 快捷操作
  steps: Array<any> | null;             // 链式执行步骤
  slots: Record<string, any> | null;    // 当前已收集槽位
  artifacts: Array<Artifact> | null;    // 右侧工作区卡片
}
```

### 4.1 典型响应场景

| 场景 | `type` | `workflow_state` | 说明 |
|------|--------|------------------|------|
| 槽位缺失 | `guide` | `consulting` | 提示用户继续填槽，附带 A/B/C |
| 计划生成 | `guide` | `plan_review` | 展示 Todo + Outline，附带 A/B/C |
| 段落审阅 | `guide` | `human_review` | 展示当前段落，附带通过/修改/重写 |
| 最终完成 | `final_script` | `complete` | 返回完整剧本，右侧生成 script 卡片 |

### 4.2 右侧工作区卡片

`artifacts` 列表驱动右侧卡片展示，每个 artifact 包含：

```ts
interface Artifact {
  id: string;           // 卡片唯一标识
  type: "outline" | "research" | "script" | "review" | "section";
  title: string;
  content: string;
  op: "create" | "append" | "update";
  version: number;
  created_by: string;
}
```

前端 `applyArtifactOp()` 根据 `id` 决定新建卡片或更新已有卡片。因此不同段落的 artifact 需要使用不同 ID（例如 `{session_id}-section-{section_index}`），否则会被合并到同一张卡片。

---

## 5. Supervisor 与 Worker 的关系

```text
                        START
                          │
                          ▼
                    ┌───────────┐
                    │ Supervisor │  ← 只根据 phase 路由
                    └─────┬─────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
  intent_classifier   context_analyzer      writer
  slot_filler         planner               reviewer
  slot_checker        search                chat
  guide               plan_review_node      human_node
                      process_plan_feedback process_feedback
```

- **Supervisor**：无 LLM 调用，纯代码条件边。
- **Worker**：每个节点只负责一类任务，调用 LLM 或规则逻辑生成内容。

---

## 6. 关键文件索引

| 文件 | 说明 |
|------|------|
| `src/comedy_agent/graph/supervisor_graph.py` | Supervisor 星型图构建 |
| `src/comedy_agent/agents/supervisor.py` | Supervisor 路由逻辑 |
| `src/comedy_agent/state/schema.py` | 全局状态定义 |
| `src/comedy_agent/nodes/entry_node.py` | 入口：@ 预检 + 意图分类 |
| `src/comedy_agent/nodes/plan_node.py` / `agents/planner.py` | 计划生成 |
| `src/comedy_agent/nodes/plan_review_node.py` | 计划审阅暂停 |
| `src/comedy_agent/nodes/write_node.py` / `agents/writer.py` | 段落写作 |
| `src/comedy_agent/nodes/human_node.py` | 段落审阅暂停 |
| `src/comedy_agent/api/server.py` | `/chat` 接口 |
| `src/comedy_agent/api/routers/pro_v4.py` | `/pro/chat-v4` 接口 |
| `frontend/pro-b.html` | 专业版 B 前端 |
