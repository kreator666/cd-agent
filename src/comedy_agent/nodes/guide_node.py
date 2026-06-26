"""Guide 节点适配器。

将 GuideAgent 接入 LangGraph，生成引导回复与 A/B/C 选项。
"""

from __future__ import annotations

from comedy_agent.agents.guide import GuideAgent
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = GuideAgent()


def guide_node(state: ComedyState) -> dict:
    """Guide 节点：根据当前状态返回引导与建议选项。

    Args:
        state: 当前图状态。

    Returns:
        包含 ``output``、``response_type``、``phase``、``suggested_actions`` 的更新字典。
    """
    llm = ModelFactory.get_model(state.model, task_type="fast")
    return _agent.run(state, llm=llm)
