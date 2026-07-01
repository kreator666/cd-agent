"""计划反馈处理节点。

解析用户对 Planner 生成计划的反馈，决定进入写作、重新规划还是咨询。
"""

from __future__ import annotations

import logging
import re

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


APPROVE_KEYWORDS = ("开始", "确认", "继续", "通过", "ok", "yes", "y", "写")
REPLAN_KEYWORDS = ("重新规划", "replan", "大纲不对", "重写大纲", "换")


def process_plan_feedback_node(state: ComedyState) -> dict:
    """处理用户对计划的反馈。

    Args:
        state: 当前图状态。

    Returns:
        dict: 包含 phase 等更新字段。
    """
    feedback = re.sub(r"^@\S+\s*", "", (state.feedback or "")).strip().lower()

    if any(kw in feedback for kw in APPROVE_KEYWORDS):
        logger.debug("process_plan_feedback: approve, start writing")
        return {
            "current_section": 0,
            "sections": [],
            "feedback": "",
            "phase": "generating_examples" if state.manual_section_mode else "writing",
        }

    if any(kw in feedback for kw in REPLAN_KEYWORDS):
        logger.debug("process_plan_feedback: replan")
        return {
            "feedback": "",
            "phase": "planning",
        }

    # 默认视为“修改计划”：保留用户意见，重新进入 planning
    logger.debug("process_plan_feedback: modify plan")
    return {
        "feedback": state.feedback,
        "phase": "planning",
    }
