"""审核节点：评估当前段落质量，给出通过/修改/重写建议。

Phase 2 委托给 ReviewerAgent。
"""

from __future__ import annotations

from comedy_agent.agents.reviewer import ReviewerAgent
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = ReviewerAgent()


def review_node(state: ComedyState) -> dict:
    """审核节点。

    Args:
        state: 当前图状态。

    Returns:
        包含 ``review`` 和 ``phase`` 的更新字典。
    """
    llm = ModelFactory.get_model(state.model, task_type="analytical")
    return _agent.run(state, llm=llm)
