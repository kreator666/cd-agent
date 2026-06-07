# 任务执行记录

## 任务信息
- **阶段**: 第 4 阶段 —— 前端页面重构
- **任务编号**: Fix
- **任务名称**: 修复 加点盐 / 虚拟演员 使用页面选择模型
- **执行日期**: 2026-06-07

## 任务说明
修复 OpenAI 429 insufficient_quota 错误：当用户在首页模型下拉框选择本地模型（如 ollama-qwen2.5）后，
"/chat" 已按所选模型调用，但 加点盐 和 虚拟演员 仍使用 orchestrator 当前模型，导致若 orchestrator 之前未被设置就会调用默认 OpenAI 模型。

## 完成内容
- 回滚 `AgentOrchestrator.__init__` 中的 `model_name or settings.default_model` 兜底，恢复原有设计
- `SaltRequest` 新增可选 `model: str | None` 字段
- `/salt` 端点在 `state.orch.run()` 前调用 `state.orch.set_model(request.model)`（与 `/chat` 保持一致）
- `frontend/index.html` 的 `sendSalt()` 和 `sendActorMessage()` 均读取 `#model` 下拉框并传递给后端
- 新增内置 `add_salt` Skill，让 `/salt` 通过 "使用 add_salt 技能" 指令走 orchestrator/agent 路由
- `/salt` 端点构造 skill 指令调用 `state.orch.run()`，避免直接 LLM 调用被 skill 指令解析误识别
- Salt 相关测试通过（`tests/test_api_new_routers.py::TestSalt`），并新增断言验证 prompt 中包含 `add_salt`

## Commit 记录
- **Commit ID**: `a124d46b527633cb17609382cd3320162ab4ee77`
- **Commit Message**: `fix: use page-selected model for salt and actor chat`
- **Branch**: `refactor`
- **Remote**: `origin/refactor`

- **Commit ID**: `a2cac6633a85c023d97056b75ab1ae2ed24ca899`
- **Commit Message**: `feat: add add_salt skill and route salt via orchestrator`
- **Branch**: `refactor`
- **Remote**: `origin/refactor`

## 备注
- 测试通过率: `tests/test_api_new_routers.py::TestSalt` 2/2 通过
- 未完全运行全量测试（存在与本次修改无关的 `test_preference_extractor.py` 导入错误和 `test_api_cli.py::test_skill_standup` mock 断言差异）
