# 任务执行记录

## 任务信息
- **阶段**: 测试工具增强
- **任务编号**: standup-prompt-exact-depth4
- **任务名称**: 支持精确深度提示词组合并运行 depth-4 测试
- **执行日期**: 2026-07-10

## 任务说明
在之前已支持 `plus.md` 的提示词组合测试基础上，进一步完成：
1. 新增 `--exact-depth` 参数，避免重复生成低深度组合；
2. 使用 `deepseek-v3` 模型，对密室逃脱主题运行精确深度 4 的完整组合测试；
3. 结果输出到 `tests/template/result/plus_mishi`。

## 完成内容
- 修改 `tests/template/standup_prompt_test.py`：
  - 新增 `--exact-depth` CLI 参数；
  - `generate_template_files` 增加 `exact_depth` 参数，仅生成恰好包含 N 个段落的组合；
  - 主流程中计算并打印精确深度对应的组合总数 `C(total_middle, exact_depth)`。
- 实际运行：使用 `deepseek-v3` 模型，12 个可选段落（10 个 SKILL 段落 + plus1 + plus2），精确深度 4，共 `C(12,4)=495` 种组合，全部成功并保存到 `tests/template/result/plus_mishi`。
- 运行时长约 51 分钟，期间 API 稳定，无失败重试。

## Commit 记录
- **Commit ID**: `e322f79f08b69f8d74c18a42d92b9e6c8a6e8d74`
- **Commit Message**: `task standup-prompt-exact-depth4: 支持精确深度提示词组合测试`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 测试通过率：495/495（100%）成功调用并保存结果。
- 当前 `tests/template/result/plus_mishi` 累计包含 depth-2（78）、depth-3（220）、depth-4（495）共 793 个结果文件。
- 命令参考：
  ```bash
  python tests/template/standup_prompt_test.py \
    --exact-depth 4 \
    --models deepseek-v3 \
    --delay 0.5 \
    --plus-md tests/template/plus.md \
    --user-input "写一段脱口秀，话题：密室逃脱初体验 态度：不喜欢 偏见：你所害怕的密室逃脱通常是另一个更胆小的人提议的 情绪：不理解" \
    --result-dir tests/template/result/plus_mishi
  ```
