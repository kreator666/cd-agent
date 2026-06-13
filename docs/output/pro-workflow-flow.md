# 专业版（Pro）创作流程全链路说明

> 分析日期：2026-06-12
> 分析范围：`frontend/pro.html` → 后端 `/pro/*` API → `ProWorkflowEngine` → `喜剧龙虾/get_daren` Skill → 模型调用 → 最终剧本生成

---

## 一、页面初始化（frontend/pro.html）

### 代码位置
`frontend/pro.html` 第 1205~1303 行

### 流程

```javascript
document.addEventListener('DOMContentLoaded', async () => {
  requireAuth();          // 检查 localStorage 中的 token/user_id
  loadConversations();    // 从 localStorage 加载 pro_conversations

  loadModels();           // GET /models，填充模型下拉列表
  loadPersonas();         // GET /pro/personas，填充人物画像
  loadSkills();           // GET /pro/skills，用于核心维度标签

  if (conversations.length > 0) {
    await loadConversation(conversations[0].id);  // 自动加载最近对话
  } else {
    currentConversationId = Date.now().toString();  // 新建空白会话
  }
});
```

### 关键说明
- **认证**：所有 API 请求通过 `apiFetch` 在 Header 中携带 `Bearer token`。
- **模型默认**：`loadModels` 会优先选中第一个名称包含 `deepseek` 的模型（如 `deepseek-v3`）。
- **自动恢复**：最近对话会恢复 `workflowSessionId`、`editorHtml`、`chatHtml`；若本地只保存了打字半成品，会回源到 `/pro/chat/{sessionId}` 拉取完整 `final_script`。

---

## 二、顶部配置栏

### 2.1 模型选择

**代码位置**：`frontend/pro.html` 第 263、292、534~545 行

```html
<div class="config-item" id="configModel">
  <span class="config-label">🤖</span>
  <select id="model-select" class="model-select">
    <option value="">使用默认配置</option>
  </select>
</div>
```

- 用户选择模型后，`sendPrompt` 会读取 `$('#model-select').value` 并传给后端。
- 后端在 `ProWorkflowEngine.process` 中调用 `state.orch.set_model(request.model)` 切换模型。

### 2.2 人物画像

**代码位置**：`frontend/pro.html` 第 262、547~555 行；后端 `src/comedy_agent/api/routers/pro.py` 第 95~118 行

- 点击「🎭 未选择画像」打开 `teamMenu` 下拉框。
- 下拉框列出当前用户的 Persona（`/pro/personas`）。
- 选择画像后记录到 `selectedPersonaId`，发送消息时通过 `persona_id` 字段传给后端。
- 后端收到 `persona_id` 后，在流程开始时调用 `rule_persona` Skill，将画像规则注入 `outputs.rule_persona`。

### 2.3 创作大纲

**代码位置**：`frontend/pro.html` 第 261、712 行

- `outlinePreview` 仅作展示，实际大纲由 喜剧龙虾 在对话中收集，保存在服务端工作流状态 `slots` 中。

---

## 三、新建对话

### 代码位置
`frontend/pro.html` 第 693~730 行

### 流程

```javascript
function newConversation() {
  currentConversationId = Date.now().toString();
  $('#pageTitle').textContent = '新对话';

  // 重置服务端会话状态
  workflowSessionId = null;
  selectedPersonaId = '';
  selectedSkills = new Set();

  // 清空 UI
  $('#chatMessages').innerHTML = '...welcome...';
  $('#outlinePreview').textContent = '等待 喜剧龙虾 收集...';
  $('#editor').innerHTML = '...empty...';

  updatePersonaUI();
  renderTeamSkills();
  updateEstimate();
}
```

### 关键说明
- `workflowSessionId = null` 保证下次发送消息时后端会创建全新的会话，不会继承上一个会话的槽位状态。
- 若不重置，`sendPrompt` 会带上旧 `session_id`，导致「话题 / 态度 / 偏见 / 情绪」等槽位仍显示上一个会话的数据。

---

## 四、发送消息与后端处理

### 4.1 前端发送（sendPrompt）

**代码位置**：`frontend/pro.html` 第 831~905 行

```javascript
async function sendPrompt() {
  const text = input.value.trim();
  addChatMessage('user', '我', '创作主理人', text);

  const model = $('#model-select').value || undefined;
  const res = await apiFetch('/pro/chat', {
    method: 'POST',
    body: JSON.stringify({
      session_id: workflowSessionId,  // null 时后端新建会话
      message: text,
      persona_id: selectedPersonaId || undefined,
      model
    })
  });

  const data = await res.json();
  workflowSessionId = data.session_id;
  renderWorkflowSteps(data);
}
```

### 4.2 后端入口 /pro/chat

**代码位置**：`src/comedy_agent/api/routers/pro_workflow.py` 第 624~660 行

```python
@router.post("/pro/chat")
async def pro_chat(request: ProChatRequest, user_id: str = Depends(get_current_user)):
    engine = _get_engine()
    if request.model and state.orch:
        state.orch.set_model(request.model)

    result = engine.process(
        session_id=request.session_id,
        user_id=user_id,
        message=request.message,
        outline=request.outline,
        persona_id=request.persona_id,
        model=request.model,
    )
    return ProChatResponse(**result)
```

---

## 五、ProWorkflowEngine 处理流程

### 代码位置
`src/comedy_agent/api/routers/pro_workflow.py` 第 187~315 行

### 流程图

```
用户发送 message
    │
    ▼
加载/创建 Conversation
    │
    ├── 传了 session_id 且存在 → 恢复 wf_state / messages
    └── 未传或不存在        → 新建 session_id，初始化空 wf_state
    │
    ▼
[可选] 应用人物画像 rule_persona
    │
    ▼
检测 @mention 外部 Skill（非核心维度）
    │
    ├── 命中外部 Skill → 直接调用该 Skill，返回 skill_output
    └── 未命中         → 调用 喜剧龙虾 / get_daren
    │
    ▼
解析 喜剧龙虾 返回的 JSON
    │
    ├── slots_update  → 更新 wf_state.slots
    └── outputs_update → 更新 wf_state.outputs
    │
    ▼
构建响应（type = guide / skill_output / final_script / error）
    │
    ▼
保存 Conversation 到 memory DB
```

### 关键状态
- `wf_state.current_state`：当前工作流状态（实际始终走 `guiding`）。
- `wf_state.slots`：已收集槽位，核心字段为 `话题`、`态度`、`偏见`、`情绪`。
- `wf_state.outputs`：各 Skill 输出，最终剧本保存在 `outputs.final_script`。
- `wf_state.log`：最近 10 轮对话历史，传给 喜剧龙虾 作上下文。

---

## 六、喜剧龙虾 / get_daren Skill 调度逻辑

### 代码位置
`skills/get_daren/skill.py` 第 47~90 行

### 决策顺序

```
用户输入
    │
    ▼
1. 检测 @话题 / @态度 / @偏见 / @情绪
    │ 命中 → _action_fill_slot → 更新 slots_update + 流程指引
    │
    ▼
2. 非提问句式且话题槽位为空
    │ 命中 → 自动识别为话题
    │
    ▼
3. 检测"生成"触发词
    │ 命中 → _action_trigger_aggregate → 生成最终剧本
    │
    ▼
4. 根据 workflow_step.action 执行
    │ collect  → 收集槽位
    │ select   → 引导选择
    │ aggregate → 聚合输出
    │ guide    → 流程指引（默认）
```

### 核心槽位填写

| 槽位 | 说明 | 示例 |
|------|------|------|
| 话题 | 创作主题与背景 | 世界杯了，梅西还在踢 |
| 态度 | 评价 + 情绪 + 行动倾向 | 支持，既欣慰又嫉妒 |
| 偏见 | 独特视角或偏见 | 梅西是克隆人 |
| 情绪 | 情感节奏变化 | 被同龄人背刺的酸楚 |

### 最终剧本生成

**代码位置**：`skills/get_daren/skill.py` 第 326~407 行

1. 检查四个核心槽位是否全部填满。
2. 若有缺失，返回提示「还有以下维度未填写：...」。
3. 若全部填满，优先调用 `standup_generator` Skill 生成剧本。
4. 若 `standup_generator` 未注册或调用失败，回退到 LLM 直接聚合。
5. 将最终结果写入 `outputs_update.final_script`。

---

## 七、前端渲染响应

### 代码位置
`frontend/pro.html` 第 884~1048 行

### 响应类型

| 类型 | 说明 | 渲染位置 |
|------|------|----------|
| `guide` | 引导/追问/流程列表 | 左侧聊天区 |
| `skill_output` | 外部 Skill 输出 | 左侧聊天区 |
| `final_script` | 最终剧本 | 右侧 `#editor` + 左侧提示消息 |
| `error` | 错误信息 | 左侧聊天区 |

### final_script 渲染

```javascript
function typewriteScript(text) {
  const editor = $('#editor');
  editor.innerHTML = '';
  const paragraphs = text.split('\n').filter(p => p.trim());
  // 逐段逐字打字动画
  // 动画完成后 saveCurrentConversation()
}
```

### 关键说明
- `final_script` 会触发打字动画写入右侧编辑器。
- 动画完成后调用 `saveCurrentConversation()`，将 `editorHtml` 和 `chatHtml` 持久化到 `localStorage`。
- 页面 `beforeunload` 时也会自动保存，防止动画期间关闭页面导致结果丢失。

---

## 八、会话持久化与历史恢复

### 8.1 服务端持久化

**代码位置**：`src/comedy_agent/api/routers/pro_workflow.py` 第 553~589 行

每次 `/pro/chat` 调用结束后：

```python
self.memory.save_conversation(
    user_id=user_id,
    session_id=session_id,
    messages=messages,
    summary=user_message[:40],
    source="pro",
    metadata={"workflow": wf_state, "persona_id": persona_id},
)
```

### 8.2 本地持久化

**代码位置**：`frontend/pro.html` 第 723~752 行

```javascript
function saveCurrentConversation() {
  const conv = {
    id: currentConversationId,
    title,
    updatedAt: Date.now(),
    editorHtml,
    chatHtml,
    personaId: selectedPersonaId,
    skillIds: Array.from(selectedSkills),
    sessionId: workflowSessionId,  // fix18 新增
  };
  conversations.unshift(conv);
  localStorage.setItem('pro_conversations', JSON.stringify(conversations));
}
```

### 8.3 历史恢复

**代码位置**：`frontend/pro.html` 第 776~827 行

```javascript
async function loadConversation(id) {
  // 1. 恢复 sessionId
  workflowSessionId = c.sessionId || null;

  // 2. 若 editorHtml 为空/半成品，从服务端拉取完整 final_script
  if (isPartialEditorOutput(c.editorHtml) && c.sessionId) {
    const res = await apiFetch(`/pro/chat/${c.sessionId}`);
    const outputs = res.metadata.workflow.outputs;
    if (outputs.final_script) {
      c.editorHtml = outputs.final_script.split('\n').map(...);
    }
  }

  // 3. 恢复 UI
  $('#editor').innerHTML = c.editorHtml;
  $('#chatMessages').innerHTML = c.chatHtml;
}
```

---

## 九、关键接口汇总

| 接口 | 方法 | 说明 |
|------|------|------|
| `/models` | GET | 获取可用模型列表 |
| `/pro/personas` | GET | 获取当前用户的人物画像 |
| `/pro/personas` | POST | 创建人物画像 |
| `/pro/skills` | GET | 获取专业版可用 Skill 列表 |
| `/pro/chat` | POST | 专业版工作流对话入口 |
| `/pro/chat/{session_id}` | GET | 加载指定会话状态 |
| `/pro/upload` | POST | 上传参考文件 |

---

## 十、常见问题定位

| 现象 | 可能原因 | 排查点 |
|------|----------|--------|
| 右侧历史结果只显示一个字 | 本地 `editorHtml` 保存了打字半成品，且旧对话无 `sessionId` | Console `[history]` 日志、服务端 `final_script` 长度 |
| 新建对话仍带旧会话数据 | `workflowSessionId` 未重置 | 检查 `newConversation` 是否重置了 `workflowSessionId` |
| 流程状态混乱 | 核心槽位未清空或串会话 | 确认每次新会话后端返回新的 `session_id` |
| 模型未生效 | 前端未传 `model` 或后端 `set_model` 失败 | 抓包 `/pro/chat` 请求体、后端日志 |

---

## 十一、相关文件索引

- 前端页面：`frontend/pro.html`
- 后端路由：`src/comedy_agent/api/routers/pro_workflow.py`、`src/comedy_agent/api/routers/pro.py`
- 中央调度 Skill：`skills/get_daren/skill.py`、`skills/get_daren/SKILL.md`
- 记忆持久化：`src/comedy_agent/memory/unified.py`、`src/comedy_agent/memory/medium_term.py`
- 公共请求：`frontend/common.js`
