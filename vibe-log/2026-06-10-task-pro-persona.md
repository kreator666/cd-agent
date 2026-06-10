# 任务执行记录

## 任务信息
- **阶段**: 前端重构阶段
- **任务编号**: pro-persona
- **任务名称**: 重构人物画像模型与创建弹窗
- **执行日期**: 2026-06-10

## 任务说明
重构专业版页面的人物画像功能：
1. 清理页面残留的"人物画像"旧内容
2. 点击"新建人物画像"时弹出弹窗创建
3. 画像模型字段重构为：画像名称、画像描述、参考资料（上传参考文件）
4. 画像仅当前用户自用

## 完成内容
### 后端变更
- **数据库模型** (`schema.py`)：`personas` 表新增 `description` (VARCHAR 512) 和 `reference_files` (JSON) 字段
- **Pydantic 模型** (`models.py`)：`PersonaData` 新增 `description` 和 `reference_files` 字段
- **Memory store** (`medium_term.py`)：
  - `save_persona` / `load_persona` / `list_personas` 处理新字段
  - 启动时自动迁移：通过 `PRAGMA table_info` 检查缺失列并 `ALTER TABLE ADD COLUMN`
- **API 路由** (`pro.py`)：
  - `PersonaCreateRequest` / `PersonaUpdateRequest` 新增 `description` 和 `reference_files`
  - `create_persona` / `update_persona` 处理新字段
  - 新增 `POST /pro/upload` 接口：用户私有目录文件上传（`data/references/{user_id}/`）
  - 权限校验：画像 CRUD 已基于 `creator_id`，天然仅用户自用

### 前端变更
- **弹窗重构** (`pro.html`)：
  - 移除旧的规则字段（偏好短句、禁用词、节奏、钩子、风格示例）
  - 新增：画像名称输入框、画像描述 textarea
  - 新增：参考文件上传区域（支持点击选择和拖拽上传）
  - 文件先调用 `/pro/upload` 上传，成功后显示在列表中，创建时随请求提交
- **清理残留**：右侧面板空状态提示从"选择人物画像和 Skill 后..."改为"在左侧与写作团队对话..."

## Commit 记录
- **Commit ID**: `39b800547443edd31e2358153d5b0f9fc6434bed`
- **Commit Message**: `task pro-persona: 重构人物画像模型与创建弹窗`
- **Branch**: `v2`
- **Remote**: `origin/v2` ✅ 推送成功

## 备注
- 测试通过率：JS 语法检查通过，后端模块导入通过，页面可通过服务器正常加载
- 文件上传采用两阶段：先 `/pro/upload` 上传文件，再创建画像时带上文件元数据
- 旧画像数据兼容：缺失的 `description` 和 `reference_files` 列启动时自动迁移
