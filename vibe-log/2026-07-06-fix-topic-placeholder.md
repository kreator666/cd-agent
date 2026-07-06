# 任务执行记录

## 任务信息
- **阶段**: 修复
- **任务编号**: fix-topic-placeholder
- **任务名称**: 修复 Skill prompt_template 中 {topic} 未替换导致生成内容跑题
- **执行日期**: 2026-07-06

## 任务说明
用户反馈：点击"开始写作"后，生成的脱口秀段子标题是「职场里的"优秀员工""，与已收集的话题「假如我有三千万；我怕被绑架；肆意挥霍」完全无关。

经排查，`skills/standup/SKILL.md` 的提示词模板使用 Python format 风格占位符 `{topic}`：

```
请创作一段关于「{topic}」的脱口秀段子。
```

但 `build_prompts` 中的 `_render` 只支持 Jinja2 风格 `{{ style }}`，导致 `{topic}` 原样保留在最终 Prompt 中。LLM 看到未替换的 `{topic}` 后自由发挥，写成了与主题无关的「职场优秀员工」。

## 完成内容
- 修复 `src/comedy_agent/graph/state_modifier.py`：
  - 在 `build_prompts` 的 variables 中新增 `topic`、`attitude`、`bias`、`emotion`，优先从 `analysis` 取值，否则回退到 `slots`
  - `_render` 同时兼容 Python format 风格 `{topic}` 和 Jinja2 风格 `{{ style }}`：先把单大括号占位符转换为双大括号，再用 Jinja2 渲染
- 新增 `tests/test_state_modifier.py` 回归测试，验证 `{topic}` 从 analysis 和 slots 都能正确替换

## Commit 记录
- **Commit ID**: `9bd5e48460ff38b0ea494ac1ff345706d7b89c44`
- **Commit Message**: `fix: Skill prompt_template 中的 {topic} 等占位符未被替换导致跑题`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 相关测试全部通过：
  - `tests/test_state_modifier.py`
  - `tests/test_context_analyzer.py`
  - `tests/test_slot_filler.py`
  - `tests/test_slot_checker.py`
  - `tests/test_guide_agent.py`
  - `tests/test_entry_node.py`
  - `tests/test_intent_classifier.py`
  - `tests/test_pro_v4.py`
  - `tests/test_slot_filling_e2e.py`
  - `tests/test_e2e_chat.py`
  - `tests/test_planner.py`
- 合计 64 个相关测试通过。
