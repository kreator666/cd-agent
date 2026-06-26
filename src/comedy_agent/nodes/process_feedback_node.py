"""反馈处理节点：解析人类反馈并更新状态。

根据反馈内容决定下一步：
- "通过"/"继续"/"next" → 进入下一段或收尾
- "重写"/"replan" → 重新规划
- 其他（修改意见）→ 重写当前段
- "[manual]..." → 用户已人工编辑当前段，直接采用并继续
"""

from __future__ import annotations

import logging

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

MANUAL_EDIT_PREFIX = "[manual]"


def process_feedback_node(state: ComedyState) -> dict:
    """处理人类反馈。

    Args:
        state: 当前图状态。

    Returns:
        dict: 包含 current_section、feedback、phase 更新。
    """
    raw_feedback = (state.feedback or "").strip()
    feedback = raw_feedback.lower()
    outline = (state.plan or {}).get("outline", [])
    total_sections = len(outline)

    # 人工编辑：直接采用编辑后的文本，不调用模型重写
    if feedback.startswith(MANUAL_EDIT_PREFIX):
        edited_text = raw_feedback[len(MANUAL_EDIT_PREFIX):].strip()
        sections = list(state.sections)
        if state.current_section < len(sections):
            sections[state.current_section] = edited_text
        else:
            sections.append(edited_text)

        next_section = state.current_section + 1
        if next_section >= total_sections:
            logger.debug("process_feedback: manual edit of last section, finalize")
            return {
                "sections": sections,
                "current_section": next_section,
                "feedback": "",
                "phase": "finalizing",
            }

        logger.debug("process_feedback: manual edit adopted, move to section %d", next_section)
        return {
            "sections": sections,
            "current_section": next_section,
            "feedback": "",
            "phase": "writing",
        }

    # 通过类反馈：进入下一段或收尾
    if feedback in ("通过", "继续", "next", "ok", "yes", "y") or feedback.startswith("通过"):
        next_section = state.current_section + 1
        if next_section >= total_sections:
            logger.debug("process_feedback: all sections approved, finalize")
            return {
                "current_section": next_section,
                "feedback": "",
                "phase": "finalizing",
            }
        logger.debug("process_feedback: approve, move to section %d", next_section)
        return {
            "current_section": next_section,
            "feedback": "",
            "phase": "writing",
        }

    # 重写/重新规划类反馈
    if any(kw in feedback for kw in ("重写", "replan", "重新规划", "大纲不对")):
        logger.debug("process_feedback: replan")
        return {
            "current_section": 0,
            "sections": [],
            "feedback": "",
            "phase": "planning",
        }

    # 默认：修改当前段
    logger.debug("process_feedback: modify current section")
    return {
        "current_section": state.current_section,
        "feedback": state.feedback,
        "phase": "writing",
    }
