"""草稿收集节点：在教练模式下等待用户根据提示自行撰写段落。

使用 LangGraph 的 interrupt() 实现 checkpoint 暂停与恢复。
"""

from __future__ import annotations

import logging

from langgraph.types import interrupt

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


def draft_node(state: ComedyState) -> dict:
    """展示教练提示并等待用户撰写当前段落草稿。

    Args:
        state: 当前图状态。

    Returns:
        dict: 包含用户草稿写入 sections 后的更新，以及 phase="reviewing"。
    """
    outline = (state.plan or {}).get("outline", [])
    section_index = state.current_section
    section_goal = outline[section_index] if section_index < len(outline) else "（无）"

    interrupt_payload = {
        "message": "请根据下面的教练提示撰写当前段落，写完后直接发送。",
        "section_index": section_index,
        "section_goal": section_goal,
        "coaching_hints": state.coaching_hints or "（暂无提示）",
    }

    logger.debug("draft_node interrupt, waiting for user draft")
    user_draft = interrupt(interrupt_payload)
    draft_text = str(user_draft).strip()

    sections = state.sections.copy()
    if section_index < len(sections):
        sections[section_index] = draft_text
    else:
        sections.append(draft_text)

    return {
        "sections": sections,
        "feedback": "",
        "phase": "reviewing",
    }
