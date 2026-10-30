# 任务执行记录

## 任务信息
- **阶段**: 后端迭代
- **任务编号**: 余额限制移除
- **任务名称**: 极速版「一键生成」移除 Token 余额前置校验
- **执行日期**: 2026-09-09

## 任务说明
极速版（speed.html「一键生成」→ `/speed/polish`）在余额不足时返回 402「Token 余额不足（至少需 30，余 1）」拦截生成。要求去掉该限制。

## 完成内容
- `src/comedy_agent/api/routers/speed.py`：删除 `/speed/polish` 的 402 余额前置校验，余额不足也能正常生成
  - 扣费环节行为不变：`deduct_tokens` 余额不足时返回 False（余额不为负），仅记 warning 日志
  - `min_cost` 保留，作为模型未返回 usage 时的兜底扣费值
- `tests/test_speed_api.py` 修复（测试在本任务前已因认证/存储重构过期，全部无法运行）：
  - fixture 中 `save_user_profile` / `ensure_token_account`（方法已不存在）→ 改为 `get_token_account`（不存在自动开户赠 5000）
  - `create_access_token({"sub": ...})`（旧 payload 签名）→ 改为 `create_access_token("test_user")`（新签名为 user_id 字符串）
  - `test_polish_insufficient_tokens` 断言由 402 改为 200（生成不再被余额拦截）

## Commit 记录
- **Commit ID**: `b59d658`
- **Commit Message**: `feat(speed): 一键生成移除 Token 余额前置校验`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 部署记录
- 服务器 `47.86.55.179`：`git pull origin v3_new`，uvicorn `--reload` 自动热重载
- 验证：`/health` 200；服务器端 `speed.py` 已无余额校验代码

## 备注
- 测试通过率: 4/4 (test_speed_api.py)
- 本地 `.venv` 残缺（仅 Lib 目录），测试用系统 Python 3.11 运行
- 仅移除极速版 `/speed/polish` 的限制；`/salt`（加点盐）、`/chat`、`/standup` 的余额校验保持不变，如需一并去掉请告知
