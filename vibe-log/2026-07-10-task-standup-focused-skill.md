# 任务执行记录

## 任务信息
- **阶段**: Skill 开发
- **任务编号**: standup-focused-skill
- **任务名称**: 新增聚焦版脱口秀 Skill
- **执行日期**: 2026-07-10

## 任务说明
用户要求基于 `skills/standup/SKILL.md` 创建一个新的脱口秀技能，但只保留以下三个章节：
1. `# 二、五感幽默系统（核心能力）`
2. `# 四、开放麦级别写法（极重要）`
3. `# 九、增强模式（用于生成真正炸场内容）`

## 完成内容
- 新增 `skills/standup_focused/` 目录：
  - `SKILL.md`：精简版脱口秀技能定义，只保留角色定义、五感幽默系统、开放麦级别写法、增强模式、最终原则与输出约束；
  - `skill.py`：实现 `StandupFocusedSkill`，name 为 `standup_focused`，避免与现有 `standup_generator` 冲突。
- 参数设计与原 skill 一致：`topic`、`attitude`、`bias`、`emotion`、`duration`。
- `_run` / `_arun` 正确实现，debug 模式可输出分析过程，默认模式追加最终输出约束。
- 本地验证：通过 `load_single_skill(Path('skills/standup_focused'))` 成功加载，确认系统提示词包含五感幽默系统、开放麦级别写法、增强模式、最终原则。
- 运行 `tests/test_skills_loader.py` 全部 21 项测试通过。

## Commit 记录
- **Commit ID**: `1980cd72a7d4ee9cb221203b83dbfa54102aacfd`
- **Commit Message**: `task standup-focused-skill: 新增聚焦版脱口秀技能`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 新 Skill 名称：`standup_focused`
- 测试命令参考：
  ```bash
  python -m pytest tests/test_skills_loader.py -v
  ```
- 加载验证命令：
  ```bash
  python -c "
  from pathlib import Path
  from comedy_agent.skills.loader import load_single_skill
  skill = load_single_skill(Path('skills/standup_focused'))
  print(skill.name, skill.description)
  "
  ```
