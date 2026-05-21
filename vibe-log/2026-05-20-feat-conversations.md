# 任务执行记录

## 任务信息
- **阶段**: 独立功能 —— 会话记忆系统
- **任务编号**: feat-conversations
- **任务名称**: /chat 保存会话记录并支持历史会话列表
- **执行日期**: 2026-05-20

## 任务说明
补充记忆功能：
1. 在 `/chat` 接口里把聊天记录 `save_conversation` 写进数据库
2. 让前端能读取历史会话列表

## 完成内容
- **后端 /chat 接口改造**：
  - `ChatRequest` 增加 `session_id`（可选，为空则后端自动生成 UUID）
  - `ChatResponse` 增加 `session_id`
  - 对话完成后自动调用 `state.memory.save_conversation()` 将完整消息链写入数据库
  - 摘要取输出文本前 80 字
- **新增会话管理 API**：
  - `GET /conversations` — 获取当前用户近期会话列表（含摘要、消息数、时间）
  - `GET /conversations/{session_id}` — 获取单个会话完整聊天记录
  - `DELETE /conversations/{session_id}` — 删除指定会话
- **存储层扩展**：
  - `MemoryStore` 抽象基类增加 `delete_conversation`
  - `SQLMemoryStore` 实现 `delete_conversation`（按 user_id + session_id 删除）
  - `UnifiedMemory` 透传 `delete_conversation`
- **前端改造**：
  - sidebar 增加「新对话」按钮（绿色）
  - sidebar 增加「历史会话」列表区域，显示摘要+更新时间
  - 点击历史会话可加载完整聊天记录到对话区
  - 悬停显示删除按钮（✕），点击确认后删除
  - 发送消息时自动带上当前 `session_id`
  - 新对话时清空当前 session，后端自动生成新 ID
  - 每次对话完成后自动刷新历史会话列表
- **测试**：
  - `test_auth.py` 新增 `TestConversations` 类（5 个用例）
  - 测试覆盖：保存会话、列表查询、详情查询、删除、空列表
  - 全量测试 351/358 通过（7 skipped），0 failed

## Commit 记录
- **Commit ID**: `fad85f719fe176823054d3dd721e3b5730ac7c7b`
- **Commit Message**: `feat: /chat 保存会话记录并支持历史会话列表`
- **Branch**: `feature`
- **Remote**: `origin/feature`

## 备注
- 测试通过率: 351/358 (7 skipped, 0 failed)
- 服务已重启在 8001 端口
- Redis 未安装，限流自动降级为内存模式
- 默认模型: ollama-qwen2.5
