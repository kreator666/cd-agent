"""计划节点：生成 Todo List 和段落 Outline。

Phase 2 委托给 PlannerAgent。
"""

from __future__ import annotations

from comedy_agent.agents.planner import PlannerAgent
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = PlannerAgent()


def plan_node(state: ComedyState) -> dict:
    """计划生成节点。

    Args:
        state: 当前图状态。

    Returns:
        包含 ``plan``、``phase``、``current_section``、``sections`` 的更新字典。
    """
    llm = ModelFactory.get_model(state.model, task_type="analytical")
    return _agent.run(state, llm=llm)
