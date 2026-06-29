# 任务执行记录

## 任务信息
- **阶段**: 前端/后端清理
- **任务编号**: remove-pro-legacy-endpoints
- **任务名称**: 删除旧版 pro.html 专用后端端点及测试
- **执行日期**: 2026-06-26

## 任务说明
在前端已废弃 `pro.html`、全面改用 `pro-b.html` 的基础上，进一步清理仅旧版专业版页面使用的后端 API 端点及相关测试。

## 完成内容
- `src/comedy_agent/api/routers/pro.py`
  - 删除 `/pro/generate`、`/pro/estimate` 端点
  - 删除 `ProGenerateRequest`、`ProGenerateResponse`、`ProEstimateRequest`、`ProEstimateResponse` 模型
  - 删除 `SKILL_COST` 映射、`uuid` / `start_usage_tracking` / `charge_model_usage` 等不再使用的导入
  - 保留 `/pro/personas` CRUD、`/pro/upload`、`/pro/skills`，继续为 `pro-b.html` 提供支撑
  - 更新模块 docstring
- `src/comedy_agent/api/routers/pro_workflow.py`
  - 删除 `/pro/chat`、`/pro/chat/{session_id}` 端点
  - 删除 `ProChatRequest`、`ProChatResponse`、`Artifact`、`Attachment`、`TodoItem` 模型
  - 移除 `charge_model_usage` 导入
  - 保留 `/admin/workflow` GET/PUT，因为 `me.html` 的工作流配置编辑器仍依赖它
- `tests/`
  - 删除 `tests/test_pro_api.py`（旧 `/pro/generate`、`/pro/estimate` 测试，且 fixture 已坏）
  - 删除 `tests/test_pro_workflow_skill_mapping.py`（旧 `/pro/chat` 引擎测试）

## Commit 记录
- **Commit ID**: `4187d0d28ffbf1842d244b6757d622e761326d1e`
- **Commit Message**: `task: 删除旧版 pro.html 专用后端端点及测试`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 相关测试通过：
  - `tests/test_admin_workflow.py`：6 passed（`/admin/workflow` 仍可用）
  - `tests/test_pro_v4.py`：4 passed
  - `tests/test_api_server.py` + `tests/test_api_new_routers.py`：24 passed
- `pro_workflow.py` 中的 `ProWorkflowEngine` 类已不再被任何端点调用，但保留在文件中；如需彻底清理可在后续单独处理。
