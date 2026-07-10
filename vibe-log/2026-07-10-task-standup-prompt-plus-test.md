# 任务执行记录

## 任务信息
- **阶段**: 测试工具增强
- **任务编号**: standup-prompt-plus-test
- **任务名称**: 支持 plus.md 段落的提示词组合测试
- **执行日期**: 2026-07-10

## 任务说明
用户要求：
1. 在原有提示词组合测试程序基础上，增加 `tests/template/plus.md` 中的内容一起参与排列组合；
2. `plus.md` 按 `# plus1`、`# plus2` 分版块；
3. 使用新的用户输入（密室逃脱主题）；
4. 输出到 `tests/template/result/plus_mishi`。

## 完成内容
- 修改 `tests/template/standup_prompt_test.py`：
  - 新增 `--plus-md` 参数，支持读取外部 plus 提示词文件；
  - 新增 `parse_plus_sections` 函数，专门按 `# plus1`、`# plus2` 等标题切分 plus.md；
  - `generate_template_files` 将 plus 段落与 SKILL.md 的 10 个教学段落合并后一起排列组合；
  - 组合标签自动包含 plus1/plus2 标识，便于区分。
- 新增/保留 `tests/template/plus.md` 作为补充提示词来源。
- 更新 `tests/template/.gitignore`，排除所有生成结果目录和 zip 文件。
- 实际运行：使用 `deepseek-v3` 模型（kimi-k2.6 当时连接不稳定），深度 2，共 12 个可选段落（10 个 SKILL 段落 + plus1 + plus2），生成 C(12,1)+C(12,2)=78 种组合，全部成功并保存到 `tests/template/result/plus_mishi`。

## Commit 记录
- **Commit ID**: `f76efe6f791728a20a28eea05710493716cd55a4`
- **Commit Message**: `feat: 支持 plus.md 段落参与提示词组合测试`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 测试通过率：78/78（100%）成功调用并保存结果。
- 命令参考：
  ```bash
  python tests/template/standup_prompt_test.py \
    --combination-depth 2 \
    --models deepseek-v3 \
    --delay 0.5 \
    --plus-md tests/template/plus.md \
    --user-input "写一段脱口秀，话题：密室逃脱初体验 态度：不喜欢 偏见：你所害怕的密室逃脱通常是另一个更胆小的人提议的 情绪：不理解" \
    --result-dir tests/template/result/plus_mishi
  ```
