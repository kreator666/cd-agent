# 任务执行记录

## 任务信息
- **阶段**: 测试工具增强
- **任务编号**: standup-prompt-product-consistent
- **任务名称**: 使提示词组合测试程序解析行为与产品一致
- **执行日期**: 2026-07-10

## 任务说明
用户反馈测试程序对 `skills/standup/SKILL.md` 的解析与产品流程不一致：
1. 测试程序丢弃了 `# 十一、最终原则（最重要）` 的正文内容；
2. 产品 loader 会提取 `## 提示词模板`，测试程序未提取；
3. 希望除 `tests/template/plus.md` 的额外段落外，其它行为与产品一致。

## 完成内容
- 修改 `tests/template/standup_prompt_test.py`：
  - `parse_sections` 不再跳过 `# 十一、最终原则（最重要）`，而是将其正文与 `【最终输出约束...` 一起作为固定 `outro` 拼接到每个提示词模板末尾；
  - 新增 `parse_prompt_template`，与 `src/comedy_agent/skills/loader.py` 一致，从 SKILL.md 提取 `## 提示词模板` 内容；
  - 新增 `parse_user_params` / `build_user_input`，从 `--user-input` 中解析话题、态度、偏见、情绪、时长等字段，并填充到提示词模板；
  - 新增 `--use-prompt-template` CLI 选项，启用后使用 SKILL.md 中的模板格式化用户输入；
  - 默认仍保持原始 `--user-input` 直接作为 human message，避免破坏现有用法。
- 保持 `plus.md` 作为测试特有的额外可选段落，继续参与组合。
- 本地验证：使用 `--skip-call` 生成模板，确认 `# 十一` 正文已出现在每个模板中；使用 `--use-prompt-template` 验证用户输入格式化结果正确。

## Commit 记录
- **Commit ID**: `33fd234a24c5785d4829451c0a81e3dd13827e61`
- **Commit Message**: `task standup-prompt-product-consistent: 使测试程序解析行为与产品一致`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 测试验证方式：
  ```bash
  # 验证 # 十一 已保留
  python tests/template/standup_prompt_test.py \
    --exact-depth 2 \
    --models deepseek-v3 \
    --skip-call \
    --plus-md tests/template/plus.md \
    --user-input "写一段脱口秀，话题：密室逃脱初体验 态度：不喜欢 偏见：你所害怕的密室逃脱通常是另一个更胆小的人提议的 情绪：不理解" \
    --result-dir tests/template/result/plus_mishi
  
  # 验证提示词模板格式化
  python tests/template/standup_prompt_test.py \
    --exact-depth 2 \
    --models deepseek-v3 \
    --skip-call \
    --use-prompt-template \
    --plus-md tests/template/plus.md \
    --user-input "写一段脱口秀，话题：密室逃脱初体验 态度：不喜欢 偏见：你所害怕的密室逃脱通常是另一个更胆小的人提议的 情绪：不理解" \
    --result-dir tests/template/result/plus_mishi
  ```
- 生成的测试模板文件已清理，未进入版本控制。
