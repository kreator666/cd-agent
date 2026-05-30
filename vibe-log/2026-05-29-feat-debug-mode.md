# 任务执行记录

## 任务信息
- **阶段**: 功能增强
- **任务编号**: feat-debug
- **任务名称**: 脱口秀技能增加 Debug 模式开关，修复分析过程混入终稿的问题
- **执行日期**: 2026-05-29

## 任务说明
用户反馈系统生成的脱口秀内容把「分析过程」当作了「终稿交付」。

**根因：** `standup-template.md` 第7-9节明确要求输出分析过程（主题、人设、喜剧机制、爆点分析），而代码侧的"不含结构标签"约束太弱，无法覆盖模板中的显性输出指令。

**方案A：** 在代码侧追加硬约束覆盖模板指令，同时增加 Debug 模式开关。

## 完成内容

### 1. 终稿模式（debug=False，默认）
- `SYSTEM_PROMPT` 追加硬约束 `_OUTPUT_CONSTRAINT`：
  - 只输出段子正文，适合演员直接上台表演
  - 严禁输出：主题、人设、核心观点、使用的喜剧机制、爆点分析
  - 严禁输出：分析过程、思考步骤、meta说明、创作思路
  - 严禁使用 Markdown 标题划分结构
  - 输出必须是连续、干净的纯文本段落
- `user prompt` 删除"每个笑点标注手法类型"（与"只输出正文"矛盾）

### 2. Debug 模式（debug=True）
- `SYSTEM_PROMPT` 追加 `_DEBUG_NOTE`：
  - 输出完整创作分析过程（主题、人设、核心观点、喜剧机制、爆点分析）
  - 分析过程用【分析过程】标签开头
  - 正文用【正文】标签开头

### 3. 接口支持
- `StandupArgs` 新增 `debug: bool = Field(default=False)`
- API `/skills/standup` 接口支持 `debug` 字段
- CLI `skill standup` 子命令支持 `--debug` 参数

## Commit 记录
- **Commit ID**: `5756e9d2ad5856633825deda78f37796914f3c2a`
- **Commit Message**: `feat: 脱口秀技能增加 Debug 模式开关`
- **Branch**: `feature`
- **Remote**: `origin/feature`

## 备注
- `test_agent_orchestrator.py` 14 项全部通过
- 未改动 `standup-template.md`（保留其作为创作知识库的价值）
