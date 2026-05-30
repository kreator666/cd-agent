# 任务执行记录

## 任务信息
- **阶段**: 功能增强
- **任务编号**: cleanup-4
- **任务名称**: StandupSkill 同时加载 standup-template.md 和 standup_skills.md
- **执行日期**: 2026-05-29

## 任务说明
让内置的 `standup_generator` Skill 在生成脱口秀时，除了使用 `standup-template.md` 作为创作模板外，还将 `standup_skills.md` 的核心创作技巧直接注入 System Prompt。

## 完成内容
- `standup.py` 新增读取 `data/knowledge/standup_skills.md` 的逻辑
- `SYSTEM_PROMPT` 结构变为：
  1. 角色定义（资深脱口秀编剧）
  2. `standup-template.md` 创作规范
  3. `standup_skills.md` 核心创作技巧
  4. 执行指令
- 保留原有 RAG 检索逻辑（`self._retrieve_knowledge`）作为补充知识来源
- 同步清理 user prompt 中残留的多视角要求，改为"选择合适的叙事视角"
- 更新类 docstring，移除"多视角选择"描述

## Commit 记录
- **Commit ID**: `abf92f2a6e658e72b64ca23803c0ff18107d27f4`
- **Commit Message**: `task cleanup: StandupSkill 同时加载 standup-template.md 和 standup_skills.md`
- **Branch**: `feature`
- **Remote**: `origin/feature`

## 备注
- `test_prompt_manager.py` + `test_agent_orchestrator.py` 31 项全部通过
- 两种知识来源的关系：
  - `standup-template.md` + `standup_skills.md` → 直接读取，保证必被使用
  - RAG 向量检索 → 条件性使用（需先导入知识库）
