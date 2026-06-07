# 任务执行记录

## 任务信息
- **阶段**: 第 4 阶段 —— 前端页面重构
- **任务编号**: Fix
- **任务名称**: 统一历史对话（加点盐 / Comedy Agent / 虚拟演员）
- **执行日期**: 2026-06-07

## 任务说明
当前"加点盐历史"和"历史对话"是两个独立功能、独立数据表、独立 UI 面板。统一为单一"历史对话"，左侧摘要列表显示所有记录并标明来源，点击后右侧联动切换到对应功能 tab 显示详情。

## 完成内容
- `UserConversation` Schema 增加 `source`（String 16）和 `extra_metadata`（JSON）字段
- `ConversationData` Pydantic 模型同步增加 `source` 和 `metadata`
- `MemoryStore` 抽象类和 `SQLMemoryStore` 的 `save_conversation` / `load_conversation` / `list_conversations` 支持 source/metadata
- `SQLMemoryStore.__init__` 自动迁移旧表，添加 source/extra_metadata 列
- `/chat` 端点 `ChatRequest` 增加 `source` 字段（默认 "chat"），保存时透传
- `/salt` 端点不再调用 `save_salt_history()`，改为 `save_conversation(source="salt", metadata={...})`
- `/salt/history` 从统一 conversations 中过滤 `source="salt"` 返回
- `/conversations` 和 `/conversations/{id}` 返回字段增加 `source` 和 `metadata`
- 前端：移除左侧独立"🧂 加点盐历史"面板，只保留"历史会话"
- 前端：`renderConversationList` 根据 `source` 显示标签（💬/🧂/🎭）
- 前端：`loadConversation` 根据 `source` 联动：salt→加点盐 tab、actor→虚拟演员 tab、chat→Comedy Agent tab
- 前端：`sendActorMessage` 调用 `/chat` 时传 `source: "actor"`
- 前端：`sendSalt` 成功后刷新 `loadConversations()`
- `TestSalt` 更新断言：验证 conversation 保存且 `source="salt"`，metadata 包含原文和盐度

## Commit 记录
- **Commit ID**: `5292e1d8f7eaf0a34cc81059aeef06d126d42fd9`
- **Commit Message**: `feat: unify conversation history for chat, salt and actor`
- **Branch**: `refactor`
- **Remote**: `origin/refactor`

## 备注
- 测试通过率: `tests/test_api_new_routers.py` 10/10 通过
- `tests/test_memory_new_tables.py` 18/18 通过
- `tests/test_auth.py` conversation 相关 5/5 通过（1 个 preference 404 失败与本次修改无关）
