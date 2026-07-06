"""建议节点：使用 standup 理论体系对用户段落给出改进建议。

用户点击"给出建议"后调用，输出建议文本并回到 human_review 展示。
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.core.config import settings
from comedy_agent.core.skill_loader import load_skill_config
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


_SUGGEST_PROMPT = """{coach_system_prompt}

现在请作为教练，针对以下用户段落给出 3-5 条具体、可执行的改进建议。
建议要简短，每条一句话，直接指出可以调整的地方（如笑点节奏、铺垫、态度、情绪转折等）。

## 段落目标
{section_goal}

## 四维度分析
- 话题：{topic}
- 态度：{attitude}
- 偏见/视角：{bias}
- 情绪：{emotion}

## 用户当前段落
{section_text}

请直接输出建议列表，不要输出完整段落。
"""


def suggest_node(state: ComedyState, llm: BaseChatModel | None = None) -> dict:
    """基于 standup 理论对用户段落给出建议。

    Returns:
        dict: suggestions + phase="human_review"
    """
    outline = (state.plan or {}).get("outline", [])
    section_index = state.current_section
    section_goal = outline[section_index] if section_index < len(outline) else "（无）"
    section_text = (
        state.sections[section_index]
        if state.sections and section_index < len(state.sections)
        else ""
    )

    analysis = state.analysis or {}

    # 加载 standup 的理论体系作为教练视角
    coach_system = ""
    try:
        coach_cfg = load_skill_config(settings.skills_dir / "standup")
        if coach_cfg:
            coach_system = coach_cfg.system_prompt or ""
    except Exception as e:
        logger.warning("加载 standup 失败: %s", e)

    if not coach_system:
        coach_system = (
            "你是脱口秀教练，熟悉 BVT、ER 情绪流、观众理解五阶段、四阶段输入等中文脱口秀理论。"
        )

    prompt = _SUGGEST_PROMPT.format(
        coach_system_prompt=coach_system,
        section_goal=section_goal,
        topic=analysis.get("topic", "未指定"),
        attitude=analysis.get("attitude", "未指定"),
        bias=analysis.get("bias", "未指定"),
        emotion=analysis.get("emotion", "未指定"),
        section_text=section_text,
    )

    if llm is None:
        llm = ModelFactory.get_model(state.model, task_type="analytical")

    try:
        response = llm.invoke([("system", "你是脱口秀教练，只输出改进建议。"), ("human", prompt)])
        suggestions = str(getattr(response, "content", response)).strip()
    except Exception as e:
        logger.warning("给出建议失败: %s", e)
        suggestions = "（建议生成失败，请继续完善当前段落）"

    return {
        "suggestions": suggestions,
        "feedback": "",
        "phase": "human_review",
    }
