# 任务执行记录

## 任务信息
- **阶段**: 修复
- **任务编号**: fix-topic-deepen
- **任务名称**: 修复话题已填充后未继续使用 topic Skill 深挖子话题
- **执行日期**: 2026-07-06

## 任务说明
用户发现回复「哇！三个关键词齐活了！…咱们是直接开写段子，还是先聊聊具体想怎么组合这些元素？」看起来不像使用了 topic Skill，没有按 topic Skill 要求的「先确认整体话题，再深挖子话题」的流程输出 A/B/C 选项。

经排查，原逻辑仅在「话题」槽位缺失时使用 topic Skill 的 collection_prompt；一旦用户通过 `@话题` 填充了话题槽位，后续引导就回到默认 PROMPT，导致回复不符合 topic Skill 的引导风格。

## 完成内容
- 修改 `src/comedy_agent/agents/guide.py`：
  - `_load_collection_prompt` 新增判断：当话题已填充但用户刚聊完话题（`active_slot_dimension == "话题"`）且还有其他维度未收集时，继续回退到 topic Skill 的 collection_prompt
  - 导入 `SlotFillingAgent` 用于判断缺失维度
- 更新 `skills/topic/collection_prompt.md`：
  - 区分「话题缺失」「话题已给出但整体较宽」「话题已较具体」三种状态
  - 明确在话题已给出时应继续深挖具体场景、人群、冲突或独特经历
- 新增 `tests/test_guide_agent.py` 回归测试：验证话题已填充且刚聊完话题时，仍然加载 topic Skill

## Commit 记录
- **Commit ID**: `043b38399dad50adb26a5048b6cc531b6c94bc29`
- **Commit Message**: `fix: 话题已填充时继续使用 topic Skill 深挖子话题`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 相关测试全部通过，合计 68 个相关测试通过。
