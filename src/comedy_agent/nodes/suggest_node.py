"""建议节点：使用 standup 理论体系对用户段落给出改进建议，并输出建议修改版。

用户点击"给出建议"后调用，输出建议列表 + 按建议重写后的段落，回到 human_review 展示。
"""

from __future__ import annotations

import logging
import re

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.core.config import settings
from comedy_agent.core.skill_loader import load_skill_config
from comedy_agent.models.factory import ModelConfigError, ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


_REVISION_MARKER = "✏️ 建议修改版："

_SUGGEST_PROMPT = """{coach_system_prompt}

请同时完成以下两项任务：

1. 针对以下用户段落给出 3-5 条具体、可执行的改进建议。建议要简短，每条一句话，直接指出可以调整的地方（如笑点节奏、铺垫、态度、情绪转折等）。
2. 根据这些建议，直接重写当前段落，输出一个“建议修改版”。修改版必须比原文有肉眼可见的提升：更口语化、节奏更紧凑、笑点更强；不要只做同义词替换。

输出格式必须严格如下：

💡 改进建议：
- 建议 1
- 建议 2
...

✏️ 建议修改版：
<修改后的完整段落，只输出段落正文，不要解释>

## 段落目标
{section_goal}

## 四维度分析
- 话题：{topic}
- 态度：{attitude}
- 偏见/视角：{bias}
- 情绪：{emotion}

## 用户当前段落
{section_text}
"""


def _parse_suggestions_and_revision(text: str) -> tuple[str, str]:
    """从模型输出中拆分建议列表与建议修改版。

    如果模型没有按格式输出，则把全部内容当作建议，修改版为空。
    """
    if _REVISION_MARKER in text:
        suggestions_part, revision_part = text.split(_REVISION_MARKER, 1)
        suggestions = suggestions_part.strip()
        revision = revision_part.strip()
    else:
        suggestions = text.strip()
        revision = ""

    # 去掉建议部分可能残留的标题前缀
    suggestions = re.sub(r"^💡\s*改进建议[:：]?\s*", "", suggestions).strip()
    return suggestions, revision


def suggest_node(state: ComedyState, llm: BaseChatModel | None = None) -> dict:
    """基于 standup 理论对用户段落给出建议，并输出按建议重写后的版本。

    Returns:
        dict: suggestions + suggested_revision + phase="human_review"
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
        # 建议修改版属于创意改写，优先与生成段子的模型保持一致
        model_name = state.model or state.model_used or settings.creative_model
        try:
            llm = ModelFactory.get_model(model_name, task_type="creative")
        except ModelConfigError:
            logger.warning(
                "建议节点指定的模型 %s 不可用，回退到默认模型 %s",
                model_name,
                settings.default_model,
            )
            llm = ModelFactory.get_model(settings.default_model)

    try:
        response = llm.invoke(
            [
                (
                    "system",
                    "你是脱口秀教练。请同时给出改进建议和一段按建议重写后的完整段落。严格使用输出格式中的“💡 改进建议”和“✏️ 建议修改版”标记。",
                ),
                ("human", prompt),
            ]
        )
        raw_output = str(getattr(response, "content", response)).strip()
        suggestions, suggested_revision = _parse_suggestions_and_revision(raw_output)
    except Exception as e:
        logger.warning("给出建议失败: %s", e)
        suggestions = "（建议生成失败，请继续完善当前段落）"
        suggested_revision = ""

    return {
        "suggestions": suggestions,
        "suggested_revision": suggested_revision,
        "feedback": "",
        "phase": "human_review",
    }
