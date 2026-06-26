"""入口节点：意图分类与状态初始化。

Phase 2 委托给 IntentClassifierAgent，节点本身负责：
1. 快速判断明确的 @ 槽位填充，节省 token。
2. 其余情况再调用 LLM 意图分类。
"""

from __future__ import annotations

from comedy_agent.agents.intent_classifier import IntentClassifierAgent
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = IntentClassifierAgent()
_SLOT_KEYS = ("话题", "态度", "偏见", "情绪")


def entry_node(state: ComedyState) -> dict:
    """入口节点：先检查明确的 @ 填槽，再分类意图。

    Args:
        state: 当前图状态。

    Returns:
        包含 ``intent`` 和 ``phase`` 的更新字典。
    """
    user_input = state.user_input

    # 明确的 @ 槽位填充：直接判定，不走 LLM
    if "@" in user_input:
        for key in _SLOT_KEYS:
            if f"@{key}" in user_input:
                return {"intent": "fill_slot", "phase": "filling_slots"}

    llm = ModelFactory.get_model(state.model, task_type="analytical")
    return _agent.run(state, llm=llm)
