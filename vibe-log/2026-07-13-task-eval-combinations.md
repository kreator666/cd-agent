# 任务执行记录

## 任务信息
- **阶段**: 第 X 阶段 —— 产品功能迭代
- **任务编号**: eval-combinations
- **任务名称**: 笑果评测支持正式 standup 章节模板与排列组合
- **执行日期**: 2026-07-13

## 任务说明
用户反馈当前笑果评测页面可选择的章节模板较少，应使用正式产品 Skill `skills/standup/SKILL.md` 中的章节模板；
并且多选章节时的逻辑应改为排列组合：例如选中 a、b、c 三个章节，应生成 a+四维度、b+四维度、c+四维度、ab+四维度、ac+四维度、bc+四维度、abc+四维度。

## 完成内容
- 后端 `src/comedy_agent/api/routers/eval.py`
  - 默认 Skill 从 `standup_focused` 改为 `standup`，加载正式产品的 10 个章节模板
  - 新增 `_build_section_combos()` 辅助函数，对选中的章节生成所有非空排列组合
  - 创建会话时 `total` 改为组合数量，每个组合作为一条 `EvalResult` 记录
  - 后台生成时为每个组合构建系统提示词并调用模型
- 数据库 `src/comedy_agent/memory/schema.py`
  - `eval_results` 表新增 `combo_id`（组合 ID）和 `combo_sections`（组合包含的章节列表）字段
- 前端 `frontend/eval.html`
  - 章节模板接口改为 `/eval/skills/standup/sections`
  - 创建会话时 `skill_name` 改为 `standup`
  - 结果卡片展示组合标题及包含的章节列表
  - 更新页面说明文案，提示会生成所选章节的全部非空组合
- 测试
  - `tests/test_eval_api.py`：更新为 `standup`，验证 2 个章节生成 3 种组合
  - `tests/test_prompt_sections.py`：新增 `standup` 章节加载测试和 `generate_combinations` 排列组合测试

## Commit 记录
- **Commit ID**: `808522b96388a36f053320bda6a62dc4ca5ddb91`
- **Commit Message**: `task eval: 使用 standup 正式章节模板并支持章节排列组合`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 测试通过率: 23/23 (100%)（`tests/test_prompt_sections.py` + `tests/test_eval_api.py`）
- 组合规则：N 个选中章节生成 `2^N - 1` 种非空组合，每个组合均搭配同一组四维度输入
- 四维度（话题/态度/偏见/情绪）作为固定输入，不参与章节排列，只与每个章节组合搭配
