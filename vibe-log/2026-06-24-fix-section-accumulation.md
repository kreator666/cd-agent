# 任务执行记录

## 任务信息
- **阶段**: 功能修复
- **任务编号**: fix-section-accumulation
- **任务名称**: 重构总编按小节生成、增强脱口秀/上下文逻辑、修复偏见槽位收集
- **执行日期**: 2026-06-24

## 任务说明
本次任务围绕 Pro 工作流「总编按小节生成」进行了一系列修复与增强：

1. 首先纠正了对「按小节生成」的理解：不是按固定大纲分小节输出，而是与 LLM 多轮对话续写，每段是一个子话题。
2. 随后增强生成内容的脱口秀形式与上下文逻辑性。
3. 最后修复用户反馈的「偏见槽位收集不到」导致无法进入最终写作环节的问题。

## 完成内容

### A. 按小节生成语义重构（多轮对话续写）
- 删除 `_generate_section_outline` 方法及 `_SECTION_OUTLINE_PROMPT_PATH`，不再预生成固定大纲。
- `_handle_generate_section` 改为：首次进入写第 1 段；用户说「继续」或输入自由文本时生成下一段子话题；说「完成」才结束。
- `_generate_script_content` 新增 `sub_topic` 参数，把用户最新输入注入 Prompt。
- `_classify_section_reply` 默认行为从 `modify` 改为 `next`，让自由文本自然续写新段。

### B. 增强脱口秀形式与上下文逻辑
- 更新 `data/prompts/pro/standup_section_content.md`：
  - 新增「脱口秀结构意识」：开场段、中间展开段、深入/升级段的功能说明；
  - 新增「上下文与衔接」专节：承接前文、避免重复、callback 技巧、叙事递进；
  - 传入全部前文（由最近 2 段改为全部已生成段落）；
  - 新增 `overall_progress` 变量描述当前段结构位置。
- 代码中 `previous` 改为全部前文，帮助 LLM 掌握整体叙事线。

### C. 修复偏见槽位收集问题
- 修复 `@偏见专家 领导永远是对的` 提取错误：`_extract_mention_content` 优先匹配完整角色名，避免 `@偏见` 前缀误截断。
- 修复 `偏见：领导永远是对的` 等语义跳转时的槽位值提取：新增 `_extract_slot_value_from_text`，去掉「偏见：/偏见是/我的偏见是」等前缀。
- 修复兜底填充把引导词也填进槽位：兜底填充时先用 `_extract_slot_value_from_text` 清洗前缀。
- 修复 `@mention` / 语义跳转填槽后状态不推进：
  - `advance` 条件增加 `fill_slot`；
  - `_compute_next_state` 中，语义跳转到某核心专家且该槽位已被填充时，直接推进到下一个未填充槽位。

### D. 测试更新
- 新增/重写 `tests/test_chief_editor_section_accumulation.py`：9 个用例。
- 重写 `tests/test_pro_workflow_standup_section.py`：11 个用例。
- 新增 `tests/test_bias_slot_filling.py`：5 个用例覆盖 LLM 正常返回、兜底填充、@mention、语义跳转、不覆盖已有值。
- 更新 `tests/test_pro_workflow_intent.py` 和 `tests/test_get_daren_v3.py` 中依赖旧语义的测试。

### E. 修复「自作主张结束」与「覆盖感」回归
- 移除 `_SECTION_FINISH_RE` 中的「好了」「停」等易误触发词，仅保留明确的结束语（完成/结束/done/finish/停止/定稿/就这些/就到这/到此为止）。
- 改进 `_sanitize_section_content` 的去重阈值：只有重复头部长度 ≥80 字符时才截断，避免常见短开头相似导致新段落被误删。
- 更新/新增回归测试：
  - `test_hao_le_does_not_finish`：验证「好了，再写写同事关系」继续生成下一段。
  - `test_short_repeated_prefix_not_truncated`：验证短重复开头不被误截断。
  - 调整 `test_sanitize_repeated_previous_section` 使用长重复文本验证截断逻辑。

## 测试情况
- `tests/test_bias_slot_filling.py`：5/5 通过
- `tests/test_bias_slot_filling.py`：5/5 通过
- `tests/test_chief_editor_section_accumulation.py`：11/11 通过
- `tests/test_pro_workflow_standup_section.py`：11/11 通过
- `tests/test_pro_workflow_intent.py`：10/10 通过
- `tests/test_get_daren_v3.py`：47/47 通过
- `tests/test_pro_workflow_skill_mapping.py`：10/10 通过
- **合计：94/94 通过（本次修复后）**

## Commit 记录
- **Commit ID**: `c804bf12cbb635c4f04a9e5f6b746ce2f13de3d5`
- **Commit Message**: `fix: 重构总编按小节生成、增强脱口秀上下文逻辑、修复偏见槽位收集`
- **Branch**: `v3`
- **Remote**: `origin/v3`

## 备注
- 已合并提交前一文档任务 `docs/design/pro-chief-editor.md` 与对应 vibe-log。
- 既有测试错误（与本次改动无关）：`tests/test_pro_api.py` 4 个 setup ERROR（`SQLMemoryStore` 缺少 `save_user_profile`）；`tests/test_skills_standup.py` 1 个 FAILED（`_build_user_prompt` 未输出「3 个不同视角」）。
