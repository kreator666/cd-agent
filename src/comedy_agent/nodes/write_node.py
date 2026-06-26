"""写作节点：根据大纲逐段撰写内容。

Phase 2 委托给 WriterAgent。
"""

from __future__ import annotations

from comedy_agent.agents.writer import WriterAgent
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = WriterAgent()


def write_node(state: ComedyState) -> dict:
    """写作节点。

    Args:
        state: 当前图状态。

    Returns:
        包含 ``sections`` 更新和 ``phase`` 的更新字典。
    """
    llm = ModelFactory.get_model(state.model, task_type="creative")
    return _agent.run(state, llm=llm)
