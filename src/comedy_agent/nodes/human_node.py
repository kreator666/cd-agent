"""Human-in-the-Loop 节点：暂停等待人类反馈。

使用 LangGraph 的 interrupt() 实现 checkpoint 暂停与恢复。
"""

from __future__ import annotations

import logging

from langgraph.types import interrupt

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


def human_node(state: ComedyState) -> dict:
    """人类审阅节点。

    调用 interrupt() 暂停图执行，等待人类反馈。
    恢复后，interrupt() 返回用户反馈文本。

    Args:
        state: 当前图状态。

    Returns:
        dict: 包含 feedback 和 phase 更新。
    """
    sections = state.sections
    current_text = sections[state.current_section] if sections and state.current_section < len(sections) else ""
    review = state.review or {"decision": "修改", "comments": ""}

    interrupt_payload = {
        "message": "请审阅当前段落并提供反馈",
        "section_index": state.current_section,
        "section_text": current_text,
        "review_decision": review.get("decision", "修改"),
        "review_comments": review.get("comments", ""),
    }

    logger.debug("human_node interrupt, waiting for feedback")
    feedback = interrupt(interrupt_payload)

    return {
        "feedback": str(feedback),
        "phase": "routing_feedback",
    }
