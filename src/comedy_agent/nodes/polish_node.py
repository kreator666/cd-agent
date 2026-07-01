"""润色节点：根据用户当前段落、大纲和上下文进行润色。

用户点击"润色"后调用，输出润色后的段落并回到 human_review。
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


_POLISH_PROMPT = """你是一名中文脱口秀编剧。请对以下用户写的段落进行润色。

## 段落目标
{section_goal}

## 四维度分析
- 话题：{topic}
- 态度：{attitude}
- 偏见/视角：{bias}
- 情绪：{emotion}

## 风格
{style}

## 已完成的上下文
{context}

## 用户当前段落
{section_text}

## 额外要求
{feedback}

请直接输出润色后的段落文本，保持原意和用户的个人表达，同时让节奏、口语感和笑点更自然。不要解释，只输出段落正文。
"""


def polish_node(state: ComedyState, llm: BaseChatModel | None = None) -> dict:
    """润色当前段落。

    Returns:
        dict: sections 更新为润色后的文本，phase="human_review"
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
    style = state.selected_style or state.selected_skill or "默认"

    context_parts = []
    if section_index > 0 and state.sections:
        context_parts.append("前文段落：")
        for idx, text in enumerate(state.sections[:section_index], start=1):
            context_parts.append(f"段落 {idx}：{text[:200]}")
    else:
        context_parts.append("（这是第一个段落，无前文）")
    context = "\n".join(context_parts)

    prompt = _POLISH_PROMPT.format(
        section_goal=section_goal,
        topic=analysis.get("topic", "未指定"),
        attitude=analysis.get("attitude", "未指定"),
        bias=analysis.get("bias", "未指定"),
        emotion=analysis.get("emotion", "未指定"),
        style=style,
        context=context,
        section_text=section_text,
        feedback=state.feedback or "无额外要求，请整体润色",
    )

    if llm is None:
        llm = ModelFactory.get_model(state.model, task_type="creative")

    try:
        response = llm.invoke([("system", "你是中文脱口秀润色专家，只输出润色后的段落正文。"), ("human", prompt)])
        polished = str(getattr(response, "content", response)).strip()
    except Exception as e:
        logger.warning("润色失败: %s", e)
        polished = section_text

    sections = state.sections.copy()
    if section_index < len(sections):
        sections[section_index] = polished
    else:
        sections.append(polished)

    return {
        "sections": sections,
        "feedback": "",
        "suggestions": None,
        "phase": "human_review",
    }
