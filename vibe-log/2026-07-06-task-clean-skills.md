# 任务执行记录

## 任务信息
- **阶段**: 维护阶段 —— Skill 精简
- **任务编号**: clean-skills
- **任务名称**: 清理 Skill，仅保留 standup 与 add_salt
- **执行日期**: 2026-07-06

## 任务说明

删除 `skills/` 目录下除 `standup` 与 `add_salt` 外的所有 Skill，清理后端、前端、测试中硬编码的引用，确保系统仅围绕保留的 Skill 运行。

## 完成内容

- 删除 `skills/` 目录：`crosstalk`、`hu_lan`、`japanese_sketch`、`manzai`、`open_source_skill`、`sitcom`、`sketch`、`standup_coach`、`standup_v2`、`writer_agent`、`xu_zhisheng`、`zhou_qimo`
- 删除内置 dead-code skill 文件：`crosstalk.py`、`sketch.py`、`sitcom.py`、`manzai.py`、`japanese_sketch.py`
- 更新 `src/comedy_agent/skills/__init__.py`、`loader.py`、`base.py` 仅导出/保护 `standup_generator` 与 `add_salt`
- 更新 `skill_router.py`、`writer.py`、`guide.py`、`suggest_node.py` 默认 fallback 为 `standup`
- 移除 `api/server.py` 中 `/skills/sketch`、`/skills/manzai`、`/skills/japanese-sketch` 端点及对应模型
- 更新 `api/routers/pro.py` `/pro/skills` 仅返回 `standup` 类型
- 更新 CLI help 与评估长度期望，移除已删除类型
- 清理 `frontend/pro-b.html`、`knowledge.html`、`me.html` 的 Skill 下拉与 `@mention` 引用
- 更新测试文件中所有被删除 Skill 的引用为 `standup`
- 优化 `test_documents_api.py`、`test_scripts_api.py` fixtures，mock VectorStore/ComedyRetriever/build_chat_graph 以跳过模型加载
- 修复 `test_skills_standup.py` 中 `perspective_count` 未写入 Prompt 的问题
- 新增 `comedy_agent.memory.preference_extractor` 模块，修复 `test_preference_extractor.py` 收集失败

## Commit 记录
- **Commit ID**: `40f653fcbc3397201c313fe903c2779d3c9f283c`
- **Commit Message**: `task: 清理 Skill，仅保留 standup 与 add_salt`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 定向测试通过率：135/135（API/记忆/Skill/Writer/Planner/ContextAnalyzer 相关测试）
- 全量测试：629 passed，另有部分预存在的状态机/中断/RAG 隔离问题未在本次任务范围内修复
- 已推送至 `origin/v3_new`
