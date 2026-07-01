# 任务执行记录

## 任务信息
- **阶段**: 维护清理
- **任务编号**: cleanup-unused-a-skills
- **任务名称**: 删除 A 组旧 Skill 及 pro_workflow 路由
- **执行日期**: 2026-06-26

## 任务说明
在已删除 B 组 Skill 的基础上，进一步清理 A 组旧 Skill（四维度 topic/attitude/emotion、material/layout/genre/rule_persona/script_composer/get_daren），并同步移除唯一依赖这些 Skill 的旧版 `pro_workflow` 路由及相关测试。

## 完成内容
- 删除 `skills/{topic,attitude,emotion,material,layout,genre,rule_persona,script_composer,get_daren}` 目录
- 删除 `src/comedy_agent/skills/{topic,attitude,emotion,genre,rule_persona,script_composer,layout,material}.py`
- 删除旧版 `src/comedy_agent/api/routers/pro_workflow.py` 及 `data/pro_workflow.json`
- 更新 `src/comedy_agent/skills/__init__.py`，移除上述 Skill 的导入与 `__all__` 导出
- 更新 `src/comedy_agent/skills/loader.py` 的 `_BUILTIN_SKILL_NAMES`，移除上述 9 个旧 Skill ID
- 更新 `src/comedy_agent/api/server.py`，移除 `pro_workflow_router` 挂载
- 更新 `src/comedy_agent/api/routers/pro.py`，清理已删除 Skill 的类型说明与推断分支
- 删除相关旧测试：
  - `test_get_daren_v3.py`
  - `test_pro_workflow_intent.py`
  - `test_pro_workflow_standup_section.py`
  - `test_chief_editor_section_accumulation.py`
  - `test_rule_persona_prompt_escape.py`
  - `test_skills_layout.py`
  - `test_skills_material.py`
  - `test_bias_slot_filling.py`
  - `test_admin_workflow.py`
- 调整 `tests/test_agent_orchestrator.py`，将参数提取测试从 `LayoutSkill` 改为仍存在的 `AddSaltSkill`

## Commit 记录
- **Commit ID**: `1f44e38fadb7479381a6bc84c25ab287edf17b9f`
- **Commit Message**: `cleanup: 删除 A 组旧 Skill 及 pro_workflow 路由`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 测试情况
- `tests/test_skills_loader.py`：21 passed
- `tests/test_skills_styles.py`：6 passed
- `tests/test_skill_standup_coach.py` + `tests/test_standup_v2_skill.py`：7 passed
- `tests/test_agent_orchestrator.py`：16 passed
- `tests/test_writer.py` + `tests/test_state_modifier.py`：参与通过
- `tests/test_pro_v4.py`：4 passed
- `tests/test_api_server.py`：13 passed
- 测试集合（`--collect-only`，排除 `test_preference_extractor.py`）无导入错误

## 备注
- 当前 `skills/` 下仅保留 v4 写作流程及活跃入口使用的 Skill。
- 旧版 `pro.html` 已重定向到 `pro-b.html`，删除 `pro_workflow` 路由不影响现有前端。
