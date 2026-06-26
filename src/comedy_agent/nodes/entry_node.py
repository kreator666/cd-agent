"""入口节点：意图分类与状态初始化。

Phase 2 委托给 IntentClassifierAgent，节点本身仅负责模型获取与适配。
"""

from __future__ import annotations

from comedy_agent.agents.intent_classifier import IntentClassifierAgent
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = IntentClassifierAgent()


def entry_node(state: ComedyState) -> dict:
    """入口节点：调用 IntentClassifierAgent 分类意图。

    Args:
        state: 当前图状态。

    Returns:
        包含 ``intent`` 和 ``phase`` 的更新字典。
    """
    llm = ModelFactory.get_model(state.model, task_type="analytical")
    return _agent.run(state, llm=llm)
