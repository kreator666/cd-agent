# 任务执行记录

## 任务信息
- **阶段**: 第 C 阶段修复
- **任务编号**: fix-guide-context
- **任务名称**: 修复 GuideAgent 上下文脱节问题
- **执行日期**: 2026-06-26

## 任务说明
在专业版 B 对话中，模型先回复“咱们可以从这几个角度来挖掘笑点：”，用户追问“哪几个点？”后，模型却脱离上下文回复“我可以帮你写脱口秀段子、漫才剧本……”。

根因：GuideAgent 的 Prompt 只包含当前 `user_input`，未注入历史对话，导致模型无法结合上文理解用户追问。

## 完成内容
- `src/comedy_agent/agents/guide.py`
  - Prompt 新增 `{history}` 占位符，注入最近 10 条对话记录
  - 新增 `_format_history()` 辅助函数，将 `state.messages` 格式化为 `用户/助手` 对话文本
  - 在 Prompt 中明确要求“请结合最近对话记录理解上下文，不要脱离上下文回答”
  - `run()` 调用时传入格式化后的历史

## Commit 记录
- **Commit ID**: `8fb147cc334496271df8fe5ede1a8850048f090f`
- **Commit Message**: `task: GuideAgent Prompt 注入最近对话记录，修复上下文脱节`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 相关测试通过：
  - `tests/test_guide_agent.py`：4 passed
  - `tests/test_reviewer.py`：4 passed
  - `tests/test_pro_v4.py`：4 passed
