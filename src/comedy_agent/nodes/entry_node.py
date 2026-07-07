"""入口节点：意图分类与状态初始化。

Phase 2 委托给 IntentClassifierAgent，节点本身负责：
1. 快速判断明确的 @ 槽位填充，节省 token。
2. 检测用户询问未知名词/概念，优先触发搜索。
3. 其余情况再调用 LLM 意图分类。
4. Phase 3 新增：调用 Skill 路由器解析选中的 Skill/风格。
"""

from __future__ import annotations

import re

from comedy_agent.agents.intent_classifier import IntentClassifierAgent
from comedy_agent.core.skill_router import resolve_skill
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = IntentClassifierAgent()
_SLOT_KEYS = ("话题", "态度", "偏见", "情绪")

# 询问未知名词的常见句式
_UNKNOWN_TERM_PATTERNS = [
    re.compile(r"什么是\s*(.+?)[？?\s]*$"),
    re.compile(r"(.+?)\s*是什么[？?\s]*$"),
    re.compile(r"(?:解释|科普|介绍)一下\s*(.+?)[？?\s]*$"),
    re.compile(r"(.+?)\s*是什么意思[？?\s]*$"),
]


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

    # 用户询问未知名词/概念：优先触发搜索
    if _looks_like_unknown_term_query(user_input):
        return {"intent": "search", "phase": "searching"}

    # 用户确认满意并触发大纲/创作：直接判定为 writing
    if _looks_like_creation_confirmation(user_input):
        return {"intent": "writing", "phase": "filling_slots"}

    llm = ModelFactory.get_model(state.model, task_type="analytical")
    result = _agent.run(state, llm=llm)

    # Phase 3：解析 Skill 选择并合并到结果中
    skill_updates = resolve_skill(state)
    result.update(skill_updates)

    return result


def _looks_like_unknown_term_query(user_input: str) -> bool:
    """判断用户输入是否像在询问某个名词/概念的含义。"""
    text = user_input.strip()
    if len(text) > 80:
        # 过长输入更可能是陈述，不是名词解释请求
        return False
    for pattern in _UNKNOWN_TERM_PATTERNS:
        if pattern.search(text):
            return True
    return False


# 明确触发创作的确认口令
_CREATION_CONFIRMATION_KEYWORDS = ("生成大纲", "开始写作", "直接开始写作", "确认满意")


def _looks_like_creation_confirmation(user_input: str) -> bool:
    """判断用户输入是否是确认满意并触发创作的口令。"""
    text = user_input.strip()
    return any(kw in text for kw in _CREATION_CONFIRMATION_KEYWORDS)
