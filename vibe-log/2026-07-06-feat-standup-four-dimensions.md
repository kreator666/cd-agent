# 任务执行记录

## 任务信息
- **阶段**: 功能
- **任务编号**: feat-standup-four-dimensions
- **任务名称**: standup Skill 与四维度联动并支持预期时长
- **执行日期**: 2026-07-06

## 任务说明
用户指出 `skills/standup/SKILL.md` 中的参数（style、audience、density、perspective_count 等）没有与四维度系统联动，导致生成内容只依赖 topic，缺少态度、偏见、情绪的约束。同时希望 duration（时长）能让用户在「开始写作」卡片里输入，Skill 根据预期时长生成内容。

## 完成内容
- `src/comedy_agent/state/schema.py`：新增 `duration` 字段（默认 3 分钟）
- `src/comedy_agent/api/routers/pro_v4.py`：`ProChatV4Request` 新增 `duration` 参数，写入 state_updates
- `src/comedy_agent/graph/state_modifier.py`：`build_prompts` 向 Skill 模板注入 `topic`、`attitude`、`bias`、`emotion`、`duration`
- `skills/standup/SKILL.md`：
  - 删除未使用的 `style`、`audience`、`density`、`perspective_count`、`debug`
  - 新增必填参数 `attitude`、`bias`、`emotion`
  - 提示词模板改为围绕四维度 + 时长创作
- `skills/standup/skill.py`：同步 `StandupArgs`、`_build_user_prompt` 与 `_run` 签名
- `frontend/pro-b.html`：
  - `plan_review` 卡片增加「预期时长（分钟）」输入框
  - 点击「开始写作」时读取时长并通过 `runAgentTurn` 的 options 提交
  - `runAgentTurn` 支持通过 options 携带 `duration`
- `tests/test_pro_v4.py`：新增测试验证 `duration` 写入 ComedyState
- `tests/test_state_modifier.py`：新增测试验证态度/偏见/情绪/时长占位符被替换

## Commit 记录
- **Commit ID**: `45a9cfb5d2022672835f22d9efb24e8f0b61b976`
- **Commit Message**: `feat: standup Skill 与四维度联动，支持预期时长输入`
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
- 合计 66 个相关测试通过。
