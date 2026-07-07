# 任务执行记录

## 任务信息
- **阶段**: 修复
- **任务编号**: fix-sqlite-too-big
- **任务名称**: 修复 SQLite string/blob too big 导致 /pro/chat-v4 500 错误
- **执行日期**: 2026-07-06

## 任务说明
用户在使用 /pro/chat-v4 时遇到 500 错误，日志显示 `sqlite3.DataError: string or blob too big`。该错误通常由 LangGraph checkpoint 或持久化 memory 中某个字段过大导致。

经排查，可能的原因包括：
- 槽位值累积过长（如多轮 `@话题` 后内容拼接成超长字符串）
- `slot_conversations` 每个维度累积了过多消息
- `messages` 历史过长，单条消息内容也可能很大

## 完成内容
- 修改 `src/comedy_agent/agents/slot_filler.py`：
  - 新增 `_MAX_SLOT_VALUE_LENGTH = 500`，超过长度的槽位值只保留最近 500 字符
  - 新增 `_MAX_SLOT_CONVERSATION_TURNS = 20`，每个维度最多保留最近 20 条对话
- 修改 `src/comedy_agent/api/routers/pro_v4.py`：
  - 新增 `_truncate_messages` 辅助函数，限制消息历史最多 30 条
  - 单条消息内容超过 2000 字符时截断
  - 从 checkpoint 读取的历史消息也进行截断后再传入图
- 更新 `tests/test_slot_filler.py`：
  - 新增 `test_long_slot_value_is_truncated` 验证槽位值截断
  - 新增 `test_slot_conversation_turns_are_limited` 验证每个维度消息条数限制

## Commit 记录
- **Commit ID**: `fabab47f6d2706d28dc9fb3860003a3135976cd9`
- **Commit Message**: `fix: 限制槽位值与消息历史长度，防止 SQLite string/blob too big`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 相关测试全部通过，合计 70 个相关测试通过。
