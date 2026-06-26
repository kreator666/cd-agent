"""Plan 审阅节点：Planner 生成计划后暂停，等待用户确认/修改/重新规划。

使用 LangGraph interrupt() 实现 checkpoint 暂停与恢复。
"""

from __future__ import annotations

import logging

from langgraph.types import interrupt

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


def plan_review_node(state: ComedyState) -> dict:
    """计划审阅节点。

    调用 interrupt() 暂停图执行，把 Planner 生成的 todo + outline
    作为 payload 返回给前端。用户确认后进入写作，或选择重新规划。

    Returns:
        dict: 包含 phase=routing_plan_feedback 的更新。
    """
    plan = state.plan or {}
    interrupt_payload = {
        "message": "计划已生成，请确认或调整",
        "todo": plan.get("todo", []),
        "outline": plan.get("outline", []),
        "tone": plan.get("tone", ""),
    }
    logger.debug("plan_review_node interrupt, waiting for confirmation")
    feedback = interrupt(interrupt_payload)

    return {
        "feedback": str(feedback),
        "phase": "routing_plan_feedback",
    }
