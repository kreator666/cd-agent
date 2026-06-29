# 任务执行记录

## 任务信息
- **阶段**: 第 C 阶段修复
- **任务编号**: fix-pro-b-b
- **任务名称**: 修复专业版 B（pro-b.html）交互问题（方案 B）
- **执行日期**: 2026-06-26

## 任务说明
修复专业版 B 的两个交互问题：
1. 用户问「能做什么」时回复缺少脱口秀/Standup 能力。
2. 仅输入「写脱口秀」等未明确触发创作的查询时，slot_checker 按对话轮数自动进入 analyzing，导致直接返回「计划已生成」。

采用方案 B：取消按轮数自动分析，仅保留「4 槽全满」和「显式触发词」；并在新创作请求开始时清理旧 analysis / plan，避免旧计划被复用。

## 完成内容
- `src/comedy_agent/agents/guide.py`
  - Prompt 增加 `{skills}` 占位符与「系统支持的能力」上下文
  - 注入 `state.available_skills` 供 LLM 在咨询时列举能力
  - 兜底建议增加能力问答分支，包含「写一段脱口秀」等选项
- `src/comedy_agent/agents/slot_checker.py`
  - 删除 `_MIN_USER_TURNS` 与按对话轮数自动进入 analyzing 的逻辑
  - 仅保留：4 维度槽位全满 / 用户显式说「开始创作 / 出大纲 / 生成计划」等触发词
- `src/comedy_agent/api/routers/pro_v4.py`
  - 非反馈路径读取 checkpoint 后，若上一轮 `phase == "complete"` 或用户输入含创作关键词，清理旧 `analysis` / `plan`
  - 从 `state.orch.list_skills()` 获取可用能力列表并注入 `ComedyState.available_skills`
- `src/comedy_agent/api/routers/pro.py`
  - `/pro/skills` 将 `standup_generator` / `standup` 映射为 `writing` 类型，使其出现在前端写作列表
- `src/comedy_agent/state/schema.py`
  - 新增 `available_skills: list[str]` 字段
- `tests/test_slot_checker.py`
  - 将「多轮自动分析」测试改为「多轮仍保持 consulting」
- `tests/test_pro_v4.py`
  - 调整「合并历史状态」测试，避免用 `complete` 状态触发清理
  - 新增测试：新创作请求会清空旧 `analysis` / `plan`

## Commit 记录
- **Commit ID**: `1fe1debfc79fbaa016c8ad088de2c3d927833897`
- **Commit Message**: `task: 修复 pro-b 交互问题（方案 B）`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 相关测试通过：
  - `tests/test_slot_checker.py`：4 passed
  - `tests/test_guide_agent.py`：4 passed
  - `tests/test_pro_v4.py`：4 passed
  - `tests/test_supervisor.py` + `tests/test_api_server.py` + `tests/test_api_new_routers.py`：38 passed
- `tests/test_pro_api.py` 的 fixture 存在既有问题（`SQLMemoryStore.save_user_profile` 不存在），与本次改动无关。
