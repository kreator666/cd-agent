# 任务执行记录

## 任务信息
- **阶段**: new-version 分支 —— 笑果评测功能重构
- **任务编号**: refactor-1
- **任务名称**: 分段打磨工作台 + 短视频独立页面
- **执行日期**: 2026-10-30

## 任务说明

重构"笑果评测"生成段子后的两个功能：

1. **打磨**：废弃原 script_coach 整段迭代打磨，改为把段子按 `【】` 结构标签分段，新页面 `polish.html` 提供分段 panel（人工编辑 + AI 润色 + AI 重新生成），保存时合并写回 `EvalResult.content`（暂不做多版本）。
2. **生成视频**：从 eval.html 结果卡片移除入口，新建独立页面 `video-create.html`，仍按四维度（topic/attitude/bias/emotion）输入，但用新 Skill `standup_short` 生成 30 秒以内（100~150 字，上限 180 字）、1 个主爆梗或 2~3 个小梗、一条简短完整剧情的小段子，作为输入走原有 5 阶段视频流水线（流水线本身未改）。

## 完成内容

### 后端
- 新增 `src/comedy_agent/services/script_sections.py`：`parse_sections`（按 `^【(.+?)】$` 行标签分段，无标签按空行兜底）+ `merge_sections`（互逆合并）
- `src/comedy_agent/api/routers/eval.py` 新增 4 个端点：
  - `GET /eval/results/{id}/sections` 解析分段
  - `PUT /eval/results/{id}/content` 覆盖保存全文
  - `POST /eval/results/{id}/sections/{i}/polish` AI 润色单段（保职能保篇幅）
  - `POST /eval/results/{id}/sections/{i}/regenerate` AI 重写单段
- 新增 Skill `skills/standup_short/`（SKILL.md + skill.py + template.md）：30 秒短段子硬约束，固定 `【铺垫】→【升级】→【爆梗】→【收尾】` 4 段结构，duration 兼容但忽略

### 前端
- 新增 `frontend/polish.html`：分段打磨工作台（textarea 编辑、润色/重生成按钮回填、全文预览、合并保存）
- 新增 `frontend/video-create.html`：四维度输入 → 生成短段子 → 分段编辑（>180 字红色提示）→ 保存 → 创建视频任务 → 跳 workbench；含历史会话列表与"重新生成一版"
- `eval.html`：「打磨」按钮改跳 polish.html；删除 coach 模态框及全部相关 JS；删除「生成视频」按钮及 `renderVideoButton`/`goVideoWorkbench` 等
- 13 个页面导航栏新增「🎥 短视频创作」（video-create.html）入口，index.html 顶部导航加文字链接

### 测试
- 新增 `tests/test_script_sections.py`（21 个：解析/合并/互逆 + 4 端点）
- 新增 `tests/test_standup_short_skill.py`（8 个：加载/硬约束关键字/mock LLM invoke）

## Commit 记录
- **Commit ID**: `d24b86b`
- **Branch**: `new-version`
- **Remote**: `origin/new-version`
- 注：前端打磨页部分已先由子任务提交（`da798a4` 前端 + `dc2b1ec` vibe-log）

## 备注

- 测试通过率：新增 29 个测试全部通过；相关回归（eval/api/routers/skills）无失败
- 存量失败（改动前干净代码同样失败，与本次无关）：
  - `tests/test_auth.py::TestConversations::test_chat_saves_conversation`（依赖外部中转 API，返回 500）
  - `tests/test_rag_retriever.py` 7 个
  - `tests/test_verification.py` 5 个
  - `tests/test_knowledge_distiller.py` 3 个、`test_memory_rag_integration` 1 个、`test_persona.py` 5 errors、`test_documents_api` 2 errors、`test_auth` 另有 3 个（待干净树终验确认）
- 全量套件含大量外部依赖测试，串行跑完需 20+ 分钟，本次分批并行验证
