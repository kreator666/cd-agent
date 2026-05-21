# 任务执行记录

## 任务信息
- **阶段**: 第四阶段 —— 记忆系统与用户层
- **任务编号**: fix-memory-gaps
- **任务名称**: 完善会话自动加载与过期数据清理
- **执行日期**: 2026-05-21

## 任务说明
修复记忆系统中两个已知的工程缺口：
1. **问题2**：`/chat` 仅传 `session_id` 时不会自动从数据库加载历史上下文
2. **问题3**：过期会话仅被逻辑过滤，没有物理清理机制

## 完成内容

### 问题2：/chat 支持 session_id 自动加载历史上下文
- **修改 `api/server.py`**：
  - 在调用 `state.orch.run()` 之前，检查 `request.session_id` 是否存在且 `chat_history` 为空
  - 若满足条件，自动调用 `state.memory.load_conversation(user_id, session_id)` 读取历史会话
  - 将数据库中的 `list[dict]` 消息格式转换为 `list[tuple[str, str]]` 的 `chat_history`
  - 转换后的历史消息随当前 prompt 一起注入 Agent，实现无缝续聊
- **新增测试 `test_chat_loads_history_from_session`**：
  - 先手动写入一条历史会话，再调用 `/chat` 仅传 `session_id`
  - 验证 `state.orch.run` 接收到的 `chat_history` 参数包含完整历史消息

### 问题3：过期会话物理清理机制
- **修改 `memory/medium_term.py`**：
  - 新增 `clean_expired_conversations(user_id=None) -> int` 方法
    - 支持按用户清理或全量清理
    - 返回实际删除的记录数
  - `__init__` 启动时自动执行一次全量清理
  - `save_conversation` 保存完成后顺带清理该用户的过期会话
- **修改 `memory/unified.py`**：
  - 暴露 `clean_expired_conversations` 透传接口
- **新增测试**：
  - `test_clean_expired_conversations_all`：验证全量清理
  - `test_clean_expired_conversations_by_user`：验证按用户隔离清理
  - `test_clean_expired_conversations` (UnifiedMemory)：验证透传

### 其他修复
- `api/server.py` 补充全局 `logger = logging.getLogger("comedy-agent")` 定义，避免此前 `logger.debug/warning` 引用未定义变量导致 500 错误

## Commit 记录
- **Commit ID**: `289be127b313b4692e214f67c79112885faa4f6c`
- **Commit Message**: `fix: 会话自动加载历史上下文 + 过期数据物理清理`
- **Branch**: `feature`
- **Remote**: `origin/feature`

## 备注
- 测试通过率: 366/373 passed, 7 skipped (100% 有效测试通过)
- 清理机制采用"启动时全量 + 写入时增量"策略，兼顾及时性与性能
- 自动加载历史上下文对纯 API 调用更友好，不再依赖前端手动拼接 chat_history
