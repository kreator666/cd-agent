# 修复记录

## 问题
Phase 3/4 在 `pro-b.html` 的 @ 提及体验不一致：
- 点击 `@话题/@态度` 只往输入框插 `@维度`，但没有“当前 @ 谁”的状态。
- 点击 🎭 写作风格只改 `selectedSkillId`，输入框不变。
- 发送后输入框被清空，丢失 @ 上下文。
- 下拉菜单没有统一高亮当前选中的对象。

## 修复内容
- 新增 `currentMention` 全局状态：`{ type: 'slot'|'skill', id, label, value }`。
- 新增 `setMention()` / `mentionSlot()` / `selectSkill()` 统一入口：点击任意对象都会同步输入框、徽章、下拉高亮。
- 新增 `parseInputMention()`：用户手动输入 `@对象 ` 时自动识别并同步状态。
- `sendPrompt()` 发送后保留 `@对象 ` 前缀，下一轮默认继续当前对象。
- 顶部徽章从 `selectedSkillBadge` 改为 `currentMentionBadge`，显示 `@对象 · 名称 · 参考示例数`。
- 下拉菜单当前项增加 `✓` 与深色边框高亮。
- `@` 自动补全候选增加写作风格 Skill。

## Commit 记录
- **Commit ID**: `f4e202a`
- **Commit Message**: `fix: 统一 @ 提及状态，让 Skill/槽位选择 UI 保持一致`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 后端测试 29 passed（`test_pro_v4.py` / `test_writer.py` / `test_state_modifier.py` / `test_few_shot_formatter.py` / `test_example_retriever.py`）。
