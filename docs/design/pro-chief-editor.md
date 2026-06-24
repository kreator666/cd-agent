# Pro 工作流「主编 / 总编」执行逻辑与技术特点

> 说明：用户常把 Pro 工作流最后负责“出稿”的角色称为**主编**。在现有代码与 Prompt 中，该角色被命名为**总编**（`chief_editor`）。本文档统一使用“总编”指代这一角色，并在标题中保留“主编”以便对应用户语境。

---

## 1. 在整体流程中的位置

Pro 工作流是一条“四维度 → 总编出稿”的喜剧剧本生产流水线：

```
用户/主持人
   │
   ▼
话题专家 ── 填「话题」槽位
   │
   ▼
态度专家 ── 填「态度」槽位
   │
   ▼
偏见专家 ── 填「偏见」槽位
   │
   ▼
情绪专家 ── 填「情绪」槽位
   │
   ▼
┌─────────────────────────────────────┐
│  总编 / 主编                         │
│  • 检查四维度是否集齐                 │
│  • 询问生成方式（一次性 / 按小节）     │
│  • 整合四维度 + 附件 + 画像规则生成剧本 │
└─────────────────────────────────────┘
```

入口链路：

| 层级 | 文件/模块 | 职责 |
|---|---|---|
| 前端 | `frontend/pro.html` | 专业版聊天界面 |
| API 路由 | `src/comedy_agent/api/routers/pro_workflow.py` | 维护 `wf_state`，调用 Skill |
| Skill 调度 | `skills/get_daren/skill.py` | 喜剧龙虾 / 总编核心逻辑 |
| Prompt 模板 | `data/prompts/pro/chief_editor/default.md` | 总编角色元提示 |
| 底层模型 | `src/comedy_agent/models/factory.py` | 模型调用与自动降级 |

---

## 2. 触发条件

总编不是一开始就在场，而是满足以下两个条件后由工作流状态机自动切换：

1. **四核心槽位全部填满**：`话题`、`态度`、`偏见`、`情绪` 均非空。
2. **当前状态流转到总编审阅阶段**：情绪专家完成填槽后，`ROLE_REGISTRY` 中情绪专家的 `next_default` 指向 `"总编"`，工作流状态进入 `chief_editor_review`。

角色注册表（`skills/get_daren/skill.py`）：

```python
ROLE_REGISTRY = {
    ...
    "情绪专家": {
        "prompt": "pro/emotion_expert",
        "next_default": "总编",
        "can_fill_slot": "情绪",
        "tool": None,
    },
    "总编": {
        "prompt": "pro/chief_editor",
        "next_default": "用户",
        "can_fill_slot": None,
        "tool": None,
    },
}
```

---

## 3. 执行逻辑详解

总编阶段的核心入口是 `skills/get_daren/skill.py` 中的 `_handle_generate()`。它根据当前状态、槽位完整度、用户输入来决定下一步行为。

### 3.1 第一步：四维度强制卡点

总编在生成前会先校验四个核心槽位是否齐全：

```python
missing = [s for s in self.CORE_SLOTS if not slots.get(s)]
if missing:
    return json.dumps({
        "reply": f"⚠️ 还有以下维度未填写：{'、'.join(missing)}。请先补全后再生成。",
        ...
    })
```

- 若缺失维度，总编**拒绝生成**，并提示用户先补全对应维度。
- 这是工作流“集齐四维度才能出稿”的硬约束。

### 3.2 第二步：识别生成方式

四维度集齐后，总编需要知道用户希望：

- **一次性生成**（`one_shot`）：直接输出完整剧本。
- **按小节生成**（`section`）：先出第一段，后续根据用户指令逐段推进。

`_extract_generate_mode_and_requirements()` 使用一组正则解析用户输入：

```python
_GENERATE_MODE_PATTERNS = [
    (re.compile(r"一次性(?:生成|完整生成|输出)?|...|\bone\s*shot\b"), "one_shot"),
    (re.compile(r"(?:按|分)?小节(?:生成|输出)?|...|\bsection\b"), "section"),
]
```

识别出模式后，剩余文本会被保留为**全局风格要求**（requirements），例如用户说“按小节，加梗不要说套话”，模式匹配到 `section`，剩余部分 `加梗不要说套话` 成为全局要求。

若用户未明确选择，总编会主动询问并返回快捷按钮：

```json
{
  "reply": "请选择生成方式：回复「一次性」生成完整剧本，或「按小节」逐段输出。",
  "next_actions": [
    {"action": "set_generate_mode", "label": "📝 一次性生成", "value": "一次性"},
    {"action": "set_generate_mode", "label": "📑 按小节生成", "value": "按小节"}
  ],
  "state_update": {"current_state": "ask_generate_mode"}
}
```

### 3.3 一次性生成路径

当 mode 为 `one_shot` 时，调用 `_handle_generate_one_shot()`：

1. 调用 `_generate_script_content(section=None)` 生成完整剧本。
2. 在 `_generate_script_content()` 内部：
   - 构建包含四维度、附件摘要、用户要求的上下文。
   - 通过编排器查找并调用 `standup_generator` Skill（`src/comedy_agent/skills/standup.py`）。
   - 使用 `data/write-output/standup-template.md` 作为底层创作模板。
3. 构造 Artifact，写入 `outputs.final_script` 与 `outputs.script_main`。
4. 将工作流状态置为 `done`。

一次性生成适合想要“直接看稿”的用户。

### 3.4 按小节生成路径

当 mode 为 `section` 时，调用 `_handle_generate_section()`，这是总编最复杂也最具有特色的执行路径。

#### 3.4.1 第一次进入：生成段落大纲

- 调用 `_generate_section_outline()`，使用模板 `data/prompts/pro/standup_section_outline.md`，基于四维度生成 3–5 个段落标题。
- 同时从用户输入中提取全局风格要求，存入 `outputs["section_requirements"]`。
- 生成第 1 段正文，输出给用户。

#### 3.4.2 后续轮次：解析用户指令

已经生成过段落后，用户的回复会被 `_classify_section_reply()` 分类为以下意图：

| 意图 | 触发关键词示例 | 行为 |
|---|---|---|
| `finish` | 完成、结束、done、定稿、就这些 | 合并所有段落为完整稿件，状态置 `done` |
| `next` | 继续、下一段、next、往下写 | `section_index += 1`，生成下一段，`artifact.op = "append"` |
| `prev` | 上一段、回到上一段 | `section_index -= 1`，重写前一段 |
| `modify` / feedback | 修改、重写、太平、加梗、笑点等 | 索引不变，重写当前段，`artifact.op = "update"` |

关键代码片段：

```python
if section_status == "awaiting_confirm" or generated_sections:
    command = self._classify_section_reply(user_input)
    intent = command["intent"]

    if intent == "finish":
        full_script = "\n\n".join(generated_sections)
        # 返回 done，输出完整稿件

    if intent == "next":
        if section_index + 1 >= len(section_outline):
            # 已到最后一段，提示用户说「完成」
        section_index += 1
        # 继续生成下一段

    elif intent == "prev":
        if section_index > 0:
            section_index -= 1

    else:  # modify / feedback
        # 使用 feedback 重写当前段
```

#### 3.4.3 段落正文生成

每一段正文由 `_generate_script_content()` 使用 `data/prompts/pro/standup_section_content.md` 生成。Prompt 中注入了：

- 四维度：话题、态度、偏见、情绪
- 段落大纲
- 当前段落索引与标题
- 已生成的前文（最近 1–2 段，用于衔接）
- 用户修改意见 / 全局风格要求

Prompt 明确要求：

> “只输出当前段落的讲述正文……这是‘一直写’过程中的其中一段：如果用户没喊停，你就要继续按这个方向往下写。”

### 3.5 状态机流转

总编阶段的状态流转如下：

```
emotion_filling（情绪专家填槽完成）
    │
    ▼
chief_editor_review（进入总编）
    │
    ├─ 四维度缺失 ──► 提示补全，留在当前状态
    │
    ├─ 未选择生成方式 ──► ask_generate_mode
    │
    ├─ 一次性生成 ──► done，输出 final_script
    │
    └─ 按小节生成 ──► generating_section
            │
            ├─ 用户说「完成」──► done
            ├─ 用户说「继续」──► 生成下一段（仍在 generating_section）
            ├─ 用户说「上一段」──► 重写前一段
            └─ 用户提修改意见 ──► 重写当前段
```

---

## 4. 技术特点

### 4.1 规则 + LLM 混合的意图识别

总编阶段不依赖 LLM 来判断用户想干嘛，而是使用**多组中文正则表达式**快速、稳定地解析用户指令：

```python
_SECTION_FINISH_RE = re.compile(r"完成|结束|done|finish|停止|停|好了|定稿|就这些|就到这|到此为止")
_SECTION_NEXT_RE   = re.compile(r"继续|下一节|下一段|...|next|go\s*on|推进|往下|往下写|...")
_SECTION_PREV_RE   = re.compile(r"上一段|上一节|...|回到上一段")
_SECTION_MODIFY_RE = re.compile(r"修改|重写|...|太平|太水|加梗|...|笑点|共鸣")
```

优势：

- **低延迟**：不需要额外调用 LLM。
- **确定性高**：避免 LLM 对简短指令（如“1”、“继续”）的歧义理解。
- **可维护**：新增指令词只需扩展正则。

### 4.2 “一直写”默认推进语义

按小节生成的核心设计理念是：**只要用户没有明确说「完成 / 修改 / 上一段」，就默认继续写下一段**。

这意味着：

- 用户说“继续” → 下一段。
- 用户只发一个“1”或默认回车 → 仍被识别为继续（通过选项引用消解或默认推进逻辑）。
- 用户说“完成” → 才真正结束。

这一语义在测试中也有明确注释：

```python
"""用户没有明确说完成/修改时，默认继续生成下一段，符合主编「一直写」的预期。"""
```

### 4.3 Artifact 版本化操作

总编生成的稿件以 Artifact 形式返回，支持三种操作语义：

| 操作 | 含义 | 触发场景 |
|---|---|---|
| `create` | 首次创建 | 一次性第一次生成、分段生成第一段 |
| `append` | 追加新段落 | 分段生成下一段 |
| `update` | 更新/重写 | 分段生成中修改当前段 |

Artifact 结构示例：

```json
{
  "id": "script_main",
  "type": "script",
  "title": "脱口秀分段稿件",
  "content": "...",
  "op": "create",
  "version": 1,
  "created_by": "总编"
}
```

### 4.4 全局风格要求持久化

用户在进入分段生成时说的风格要求（如“加梗，不要说套话”）会被写入：

```python
outputs["section_requirements"]
```

并在每段生成时作为基础 feedback 注入 Prompt：

```python
leftover = command.get("feedback", "")
feedback = f"{requirements}\n{leftover}".strip() if requirements and leftover else (requirements or leftover)
```

这样即使用户在后续只回复“继续”，系统仍会记住并贯彻最初的全局风格。

### 4.5 选项引用消解

当用户回复 "1" / "2" 等数字时，系统会从上一轮助手的回复中解析对应选项内容。这让快捷按钮和自然语言回复能够统一处理。

### 4.6 人物画像规则注入

在 `ProWorkflowEngine.process()` 中，如果用户选择了人物画像（`persona_id`），流程开始时（且尚未应用时）会自动调用 `rule_persona` Skill，把规则注入：

```python
wf_state.setdefault("outputs", {})["rule_persona"] = persona_result["output"]
```

总编生成时，该规则会作为 attachment 被 Prompt 引用，使剧本符合人物画像的人设、语气、禁忌等约束。

### 4.7 模型兜底

所有 LLM 调用都走：

```python
ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
```

主模型失败时自动降级，保证总编生成这一步的高可用性。

### 4.8 Prompt 工程化与模板渲染

Prompt 管理由 `src/comedy_agent/core/prompt_manager.py` 负责，支持：

- 文件热加载
- Jinja2 / `str.format()` 双模板渲染
- 多版本与 A/B 测试
- 运行时规则覆盖

总编相关的 Prompt 文件：

| 文件 | 用途 |
|---|---|
| `data/prompts/pro/chief_editor/default.md` | 总编角色元提示，定义职责、输出格式 |
| `data/prompts/pro/standup_section_outline.md` | 分段模式下的段落大纲生成 |
| `data/prompts/pro/standup_section_content.md` | 分段模式下每段正文生成 |
| `data/write-output/standup-template.md` | 一次性生成时 `standup_generator` 使用的创作模板 |

### 4.9 决策节点追踪

每次角色切换、关键动作都会记录到 `decision_nodes` 链表，最多保留最近 30 个节点，用于后续追溯剧本是怎么一步步生成的。

---

## 5. 输入输出数据结构

### 5.1 Skill 输入：`GetDarenArgs`

```python
class GetDarenArgs(BaseModel):
    workflow_step: dict[str, Any]       # 当前状态配置
    slots: dict[str, Any]              # 已收集槽位：话题、态度、偏见、情绪
    outputs: dict[str, Any]            # 历史输出：final_script、section_outline 等
    user_input: str                    # 用户最新输入
    conversation_history: list[dict]   # 最近 10 轮对话
    user_id: str | None
    current_role: str | None
    attachments: list[dict]            # 附件（素材报告、画像规则）
    decision_nodes: list[dict]         # 决策节点链表
```

### 5.2 工作流状态关键字段

```python
{
    "current_state": "chief_editor_review" | "ask_generate_mode" | "generating_section" | "done",
    "current_role": "总编",
    "slots": {
        "话题": "...",
        "态度": "...",
        "偏见": "...",
        "情绪": "..."
    },
    "outputs": {
        "final_script": "完整稿件",
        "script_main": "同 final_script",
        "section_outline": ["开场铺垫", "观察升级", ...],
        "section_index": 0,
        "generated_sections": ["## 开场铺垫\n\n...", ...],
        "section_status": "awaiting_confirm" | "finished",
        "section_requirements": "用户全局风格要求",
        "rule_persona": "人物画像规则"  # 若有
    },
    "attachments": [...],
    "todo_board": [...]
}
```

### 5.3 Skill 返回 JSON 结构

```json
{
  "reply": "给用户的简短发言",
  "advance": true,
  "slots_update": {},
  "outputs_update": {...},
  "role": "总编",
  "next_role": "用户",
  "artifacts": [
    {
      "id": "script_main",
      "type": "script",
      "title": "脱口秀分段稿件",
      "content": "...",
      "op": "create",
      "version": 1,
      "created_by": "总编"
    }
  ],
  "attachments": [...],
  "state_update": {"current_state": "generating_section"}
}
```

---

## 6. 关键文件索引

| 文件 | 作用 |
|---|---|
| `src/comedy_agent/api/routers/pro_workflow.py` | Pro 工作流引擎、状态机、API 入口 |
| `skills/get_daren/skill.py` | 喜剧龙虾 / 总编核心调度逻辑 |
| `skills/get_daren/SKILL.md` | Skill 元信息 |
| `data/prompts/pro/chief_editor/default.md` | 总编角色 Prompt |
| `data/prompts/pro/standup_section_outline.md` | 分段大纲 Prompt |
| `data/prompts/pro/standup_section_content.md` | 分段正文 Prompt |
| `data/write-output/standup-template.md` | 一次性生成底层创作模板 |
| `src/comedy_agent/skills/standup.py` | `standup_generator` Skill |
| `src/comedy_agent/core/prompt_manager.py` | Prompt 管理器 |
| `src/comedy_agent/models/factory.py` | 模型工厂与兜底 |
| `tests/test_pro_workflow_standup_section.py` | 分段生成测试 |
| `tests/test_pro_workflow_intent.py` | 总编阶段意图测试 |

---

## 7. 总结

Pro 工作流中的「总编 / 主编」是整个喜剧剧本生产流程的**最终聚合与生成节点**。它的执行逻辑可以概括为：

1. **先卡点**：四维度未齐绝不生成。
2. **再问方式**：一次性整稿 vs 按小节分段。
3. **后出稿**：
   - 一次性模式复用 `standup_generator` 输出完整稿件。
   - 分段模式通过 LLM 先生大纲、再逐段推进，支持“一直写”。
4. **再迭代**：用户可以随时“继续 / 修改 / 上一段 / 完成”，系统用规则化意图识别 + Artifact 版本化更新实现可控的多轮创作。

技术特点包括：**规则化中文意图识别、状态机驱动、“一直写”默认推进、全局风格持久化、Artifact 版本化（create/append/update）、人物画像规则注入、模型自动兜底、Prompt 工程化管理**。这些机制共同实现了“像和一位真人主编聊天一样逐段打磨剧本”的体验。
