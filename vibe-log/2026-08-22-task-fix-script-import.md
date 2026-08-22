# 任务执行记录

## 任务信息
- **阶段**: 打赏 / 脚本修复
- **任务编号**: fix-script-import
- **任务名称**: 修正脚本导入路径
- **执行日期**: 2026-08-22

## 任务说明
用户直接运行 `python scripts/fix_tip_amount_scale.py` 时报 `ModuleNotFoundError: No module named 'comedy_agent'`，需要让脚本能自动定位项目 `src` 目录。

## 完成内容
- 在 `scripts/fix_tip_amount_scale.py` 顶部注入 `sys.path`，使其能导入 `comedy_agent`
- 同步修复 `scripts/migrate_fix_anyway_tip_units.py` 的导入路径

## Commit 记录
- **Commit ID**: `bddade59ca6046f35ad674a4c209d5efd513e942`
- **Commit Message**: `fix(scripts): 修正脚本导入路径`
- **Branch**: `v3_new`
- **Remote**: `origin/v3_new`

## 备注
- 脚本可直接运行：`python scripts/fix_tip_amount_scale.py --list`
- 当前数据库打赏记录金额已正确
