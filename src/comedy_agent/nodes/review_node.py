"""审核节点：评估当前段落质量，给出通过/修改/重写建议。"""

from __future__ import annotations

import logging

from comedy_agent.core.config import settings
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """你是一位喜剧编辑。请审核以下脱口秀段落，给出修改建议。

用户请求：{user_input}
当前段落：
{section_text}

请输出以下 JSON 格式（不要解释，只输出 JSON）：
{{
    "decision": "通过" | "修改" | "重写",
    "comments": "具体修改建议，1-3 条",
    "score": 1-10
}}
"""


def review_node(state: ComedyState) -> dict:
    """审核节点。

    Args:
        state: 当前图状态。

    Returns:
        dict: 包含 review 和 phase = human_review。
    """
    model_name = state.model or settings.default_model
    llm = ModelFactory.get_model(model_name)

    sections = state.sections
    if not sections or state.current_section >= len(sections):
        return {"review": {"decision": "通过", "comments": "", "score": 7}, "phase": "human_review"}

    section_text = sections[state.current_section]
    prompt = REVIEW_PROMPT.format(
        user_input=state.user_input,
        section_text=section_text,
    )

    response = llm.invoke([("human", prompt)])
    content = str(response.content)

    review = _parse_review(content)
    logger.debug("review_node result: %s", review)

    return {
        "review": review,
        "phase": "human_review",
    }


def _parse_review(content: str) -> dict:
    """解析审核 JSON。"""
    import json
    import re

    code_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if code_match:
        content = code_match.group(1).strip()

    try:
        review = json.loads(content)
        review.setdefault("decision", "修改")
        review.setdefault("comments", "")
        review.setdefault("score", 5)
        return review
    except json.JSONDecodeError:
        logger.warning("审核结果 JSON 解析失败，使用兜底: %s", content[:200])

    # 兜底：基于文本判断
    lowered = content.lower()
    if "通过" in lowered:
        decision = "通过"
    elif "重写" in lowered:
        decision = "重写"
    else:
        decision = "修改"

    return {"decision": decision, "comments": content[:200], "score": 5}
