"""搜索节点：调用 SearchAgent 执行素材搜索。"""

from __future__ import annotations

from comedy_agent.agents.search import SearchAgent
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = SearchAgent()


def search_node(state: ComedyState) -> dict:
    """搜索节点。

    Args:
        state: 当前图状态。

    Returns:
        包含 ``search_results`` 和 ``phase`` 的更新字典。
    """
    llm = ModelFactory.get_model(state.model, task_type="fast")
    return _agent.run(state, llm=llm)
