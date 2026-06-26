"""分析节点：对用户输入进行四维度分析。

Phase 2 委托给 ContextAnalyzerAgent。
"""

from __future__ import annotations

from comedy_agent.agents.context_analyzer import ContextAnalyzerAgent
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = ContextAnalyzerAgent()


def analyze_node(state: ComedyState) -> dict:
    """四维度分析节点。

    Args:
        state: 当前图状态。

    Returns:
        包含 ``analysis`` 和 ``phase`` 更新。
    """
    llm = ModelFactory.get_model(state.model, task_type="analytical")
    return _agent.run(state, llm=llm)
