# 任务执行记录

## 任务信息
- **阶段**: 测试工具开发
- **任务编号**: standup-prompt-combo-test
- **任务名称**: 脱口秀提示词段落组合测试程序
- **执行日期**: 2026-07-09

## 任务说明
根据用户需求，编写一个测试程序：
1. 从 `skills/standup/skill.py` 对应的 `skills/standup/SKILL.md` 中提取系统提示词；
2. 按一级标题（如 `# 一`、`# 二`）拆分为大段落；
3. 对中间教学段落进行排列组合，生成若干提示词模板并保存到 `tests/template`；
4. 以固定用户输入（中年危机相关）搭配各模板调用文生文模型；
5. 将每次结果按指定格式写入 `tests/template/result` 下的独立文件。

## 完成内容
- 新增 `tests/template/standup_prompt_test.py` 测试程序，主要功能：
  - 解析 `SKILL.md` 中的 `## 系统提示词` 区块；
  - 按 `# ` 一级标题拆分，固定保留角色定义与最终输出约束；
  - 支持 `--combination-depth`、`--max-combinations` 控制组合规模；
  - 支持 `--models` 指定一个或多个模型；
  - 支持 `--resume` 断点续跑，跳过已存在的结果文件；
  - 修复段落中 `{attitude}`、`{bias}`、`{emotion}`、`{duration}` 等占位符被 LangChain 误识别为模板变量的问题。
- 新增 `tests/template/.gitignore`，排除自动生成的模板文件与结果文件。
- 实际运行：使用 `ollama-qwen2.5` 模型，组合深度 `--combination-depth 2`，共生成并调用 55 个提示词模板，所有结果文件已保存到 `tests/template/result`。

## Commit 记录
- **Commit ID**: `c53f573d7d28120be1883167481e3e50c79bd7ec`
- **Commit Message**: `feat: 添加脱口秀提示词段落组合测试程序`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 测试通过率：55/55（100%）成功调用并保存结果。
- 默认运行采用 `ollama-qwen2.5` 本地模型；如需使用其他模型，可通过 `--models gpt-4o,claude-3-5-sonnet` 等方式指定。
- 完整排列组合（10 段中间段落全部非空子集）共 1023 种，当前演示运行了深度 2 的 55 种组合；运行完整组合需要更长时间，可通过后台任务或 `--resume` 分批完成。
