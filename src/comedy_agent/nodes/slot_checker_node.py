"""槽位检查节点适配层。"""

from __future__ import annotations

from comedy_agent.agents.slot_checker import SlotCheckingAgent
from comedy_agent.state.schema import ComedyState

_agent = SlotCheckingAgent()


def slot_checker_node(state: ComedyState) -> dict:
    """检查槽位完整性，完整则进入 planning，否则返回引导。"""
    return _agent.run(state)
