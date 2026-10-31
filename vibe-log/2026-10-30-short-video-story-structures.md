# 任务执行记录

## 任务信息
- **阶段**: new-version 分支 —— 短视频创作增强
- **任务编号**: refactor-2
- **任务名称**: 故事结构手动选择 + 分结构提示词架构
- **执行日期**: 2026-10-30

## 任务说明

短视频段子不再固定脱口秀四段结构，改为基于理论知识库（data/knowledge/theory/）中的故事架构编写：
1. 页面手动选择结构，同时保留"随机"选项（照顾犯懒场景）
2. 5 种结构全上：铺垫-反转、三番四抖、雪球效应、弹簧魔鬼、归谬滑坡
3. 字数上限 180 → 300
4. 架构改造目标：节省上下文 token

## 完成内容

### Skill 架构（省 token 核心）
- 新增 `skills/standup_short/structures/`：5 个结构各一个独立提示词文件（骨架 + 分段标签 + 写法要点 + 1 示例，各 ≤40 行），素材提炼自 theory 库文档
- `skill.py`：新增 `structure` 参数（random 为默认，非法值兜底 random）；**每次生成只读并注入所选结构的文件**，其余 4 个结构不进 LLM 上下文
- 系统提示精简为全局规则（100~150 字、上限 300、1 主爆梗或 2~3 连珠小梗、完整剧情线、收尾 mini callback、【】整行标签）
- 结构文件的分段标签不固定（如雪球用【起因】【连锁】【雪崩】【收尾】），parseSections 与视频流水线按整行【】正则分段，不受影响

### 前后端链路
- `frontend/video-create.html`：「故事结构」下拉框（随机(推荐)/5 种结构，默认随机）；CHAR_LIMIT 180→300，相关文案同步
- `eval.py`：`EvalCreateRequest.structure` 可选字段；`_run_eval_generation` 透传（仅当 Skill args_schema 含 structure 时才传，保护 standup_focused 等旧 Skill 不被多余 kwarg 破坏）

### 测试
- 26 个测试全部通过（test_standup_short_skill 13 + test_eval_api 13，含新增：structure 透传/默认 random/旧 Skill 保护）
- 浏览器实测：下拉框选项齐全、300 字提示生效

## Commit 记录
- **Commit ID**: `74f9731`
- **Branch**: `new-version`
- **Remote**: `origin/new-version`

## 备注

- token 节省：旧架构每次全量注入结构说明；新架构每次仅注入约 30 行（1 个结构文件）
- 服务已重启（task `bash-q73hm3np`），后端 structure 参数已生效
- 待观察：模型对 300 字上限的遵守情况、各结构实际生成质量
