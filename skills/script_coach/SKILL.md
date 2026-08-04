---
name: script_coach
description: "段子教练。输入一段脱口秀初稿，自动与顶流文稿库对比、按维度打分、指出可改进点，并循环优化至多 5 轮，最终返回成品与完整迭代记录。最终作品会存入用户作品库，但不会混入顶流文稿库。"
license: MIT
metadata:
  author: comedy-agent
  version: "1.0.0"
  task_type: analytical
---

# 段子教练 —— 顶流参照 + 自动评分 + 循环优化

## 功能描述

把新产出的脱口秀段子当作"学生作业"，与已入库的顶流脱口秀文稿进行标准对比：

1. 按统一维度打分；
2. 指出与顶流文稿的差距；
3. 给出具体可改进建议；
4. 自动循环改写（最多 5 轮，可配置）；
5. 输出最终成品与每轮评分记录；
6. 最终作品存入用户作品库，**不写入顶流文稿库**。

## 参数

| 参数名 | 类型 | 必填 | 描述 | 默认值 |
|--------|------|------|------|--------|
| script | str | 是 | 待打磨的脱口秀初稿 | - |
| topic | str | 是 | 核心话题 | - |
| style | str | 否 | 目标风格 | 日常观察 |
| target_duration | int | 否 | 目标时长（分钟） | 3 |
| iterations | int | 否 | 最大迭代轮数，1–5 | 1 |
| min_score | float | 否 | 提前终止的综合分阈值 | 8.0 |
| top_k | int | 否 | 检索顶流文稿数量 | 5 |
| save_product | bool | 否 | 是否保存最终成品到用户作品库 | true |
| user_id | str | 否 | 用户标识（保存作品时用） | - |

## 系统提示词

你是一位资深脱口秀教练。你的任务是把学员的新段子与顶流脱口秀文稿做标准对比，按维度给出客观评分和可落地的改进建议。

评分维度（每项 1–10 分）：
- humor_score：整体幽默程度
- setup_quality：铺垫建立预期质量
- punchline_quality：笑点/反转质量
- pacing：节奏紧凑度
- colloquial_score：口语化/舞台感
- resonance：观众共鸣感
- surprise：意外感/预期违背
- observation：观察角度独特性
- structure_integrity：结构完整性
- performance_readiness：可直接上演度

打分原则：
- 6 分 = 普通开放麦水准；
- 8 分 = 成熟商演水准；
- 9–10 分 = 顶流专场水准。

请严格按 JSON 格式输出，不要附加解释。

## 提示词模板

请对以下脱口秀段子进行教练式评审。

【待评审段子】
{script}

【话题】{topic}
【风格】{style}
【目标时长】约 {target_duration} 分钟

【参考顶流文稿】
{references}

请输出 JSON：
{{
  "overall_score": 7.5,
  "dimension_scores": {{...}},
  "gap_to_top": "与顶流文稿的主要差距",
  "weaknesses": ["可改进点1", "可改进点2"],
  "improvement_plan": "本轮具体改写方向"
}}

## 输出格式

最终返回一个 JSON 对象，包含：
- final_script：最终成品段子
- iterations：每轮评分、差距、建议、参考文稿
- stopped_reason：结束原因
