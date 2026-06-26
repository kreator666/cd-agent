"""槽位填充节点适配层。"""

from __future__ import annotations

from comedy_agent.agents.slot_filler import SlotFillingAgent
from comedy_agent.state.schema import ComedyState

_agent = SlotFillingAgent()


def slot_filler_node(state: ComedyState) -> dict:
    """解析用户输入中的槽位信息并更新 state.slots。"""
    return _agent.run(state)
