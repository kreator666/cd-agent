"""入口节点：意图分类与状态初始化。

Phase 2 委托给 IntentClassifierAgent，节点本身负责：
1. 快速判断明确的 @ 槽位填充，节省 token。
2. 其余情况再调用 LLM 意图分类。
3. Phase 3 新增：调用 Skill 路由器解析选中的 Skill/风格。
"""

from __future__ import annotations

from comedy_agent.agents.intent_classifier import IntentClassifierAgent
from comedy_agent.core.skill_router import resolve_skill
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = IntentClassifierAgent()
_SLOT_KEYS = ("话题", "态度", "偏见", "情绪")


def entry_node(state: ComedyState) -> dict:
    """入口节点：先检查明确的 @ 填槽，再分类意图，最后解析 Skill。

    Args:
        state: 当前图状态。

    Returns:
        包含 ``intent``、``phase`` 和 ``selected_skill/style`` 的更新字典。
    """
    user_input = state.user_input

    # 明确的 @ 槽位填充：直接判定，不走 LLM
    if "@" in user_input:
        for key in _SLOT_KEYS:
            if f"@{key}" in user_input:
                return {"intent": "fill_slot", "phase": "filling_slots"}

    llm = ModelFactory.get_model(state.model, task_type="analytical")
    result = _agent.run(state, llm=llm)

    # Phase 3：解析 Skill 选择并合并到结果中
    skill_updates = resolve_skill(state)
    result.update(skill_updates)

    return result
