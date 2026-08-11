"""反馈处理节点：解析人类反馈并更新状态。

根据反馈内容决定下一步：
- "通过"/"继续"/"next" → 进入下一段或收尾
- "重写"/"replan" → 重新规划
- 其他（修改意见）→ 重写当前段
- "[manual]..." → 用户已人工编辑当前段，直接采用并继续
"""

from __future__ import annotations

import logging
import re

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
    raw_feedback = re.sub(r"^@\S+\s*", "", (state.feedback or "")).strip()
    feedback = raw_feedback.lower()
    outline = (state.plan or {}).get("outline", [])
    total_sections = len(outline)

    # 人工编辑：直接采用编辑后的文本，回到 human_review 让用户确认或继续修改
    if raw_feedback.startswith(MANUAL_EDIT_PREFIX):
        edited_text = raw_feedback[len(MANUAL_EDIT_PREFIX):].strip()
        sections = list(state.sections)
        if state.current_section < len(sections):
            sections[state.current_section] = edited_text
        else:
            sections.append(edited_text)

        logger.debug("process_feedback: manual edit adopted, return to human_review")
        return {
            "sections": sections,
            "current_section": state.current_section,
            "feedback": "",
            "phase": "human_review",
        }

    # 通过类反馈：进入下一段或收尾
    if feedback in ("通过", "继续", "next", "ok", "yes", "y") or feedback.startswith("通过"):
        next_section = state.current_section + 1
        if next_section >= total_sections:
            logger.debug("process_feedback: all sections approved, finalize")
            return {
                "current_section": next_section,
                "feedback": "",
                "suggestions": None,
                "phase": "finalizing",
            }
        logger.debug("process_feedback: approve, move to section %d", next_section)
        return {
            "current_section": next_section,
            "feedback": "",
            "suggestions": None,
            "phase": "generating_examples" if state.manual_section_mode else "writing",
        }

    # 润色
    if feedback == "润色" or feedback.startswith("润色"):
        logger.debug("process_feedback: polish current section")
        return {
            "current_section": state.current_section,
            "feedback": feedback,
            "suggestions": None,
            "phase": "polishing",
        }

    # 给出建议
    if feedback == "给出建议":
        logger.debug("process_feedback: suggest for current section")
        return {
            "current_section": state.current_section,
            "feedback": "",
            "phase": "suggesting",
        }

    # 采纳建议版：直接用 suggest_node 生成的建议修改版替换当前段落
    if feedback == "采纳建议版":
        revision = (state.suggested_revision or "").strip()
        if not revision:
            logger.warning("process_feedback: adopt_revision requested but no suggested_revision available")
            return {
                "current_section": state.current_section,
                "feedback": "",
                "suggestions": None,
                "suggested_revision": None,
                "phase": "human_review",
            }
        sections = list(state.sections)
        if state.current_section < len(sections):
            sections[state.current_section] = revision
        else:
            sections.append(revision)
        logger.debug("process_feedback: adopt suggested revision for section %d", state.current_section)
        return {
            "sections": sections,
            "current_section": state.current_section,
            "feedback": "",
            "suggestions": None,
            "suggested_revision": None,
            "phase": "human_review",
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
        "feedback": raw_feedback,
        "suggestions": None,
        "phase": "generating_examples" if state.manual_section_mode else "writing",
    }
