"""入口节点：意图分类与状态初始化。

Phase 1 使用规则分类，Phase 2 将替换为 LLM 意图分类器。
"""

from __future__ import annotations

import logging
import re

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

# 创作类关键词
_WRITING_KEYWORDS = (
    "写", "创作", "来一段", "写一段", "写个", "来个", "段子", "脱口秀",
    "小品", "相声", "漫才", "剧本", "关于", "话题",
)

# 搜索类关键词
_SEARCH_KEYWORDS = ("搜索", "查一下", "查", "找", "资料", "素材")

# 控制类关键词
_CONTROL_KEYWORDS = ("停止", "结束", "退出", "重置", "清空")

# 反馈类关键词（在人类审阅阶段使用）
_FEEDBACK_KEYWORDS = ("通过", "修改", "重写", "继续", "ok", "yes", "no")


def _classify_intent(state: ComedyState) -> str:
    """规则-based 意图分类。

    Args:
        state: 当前状态。

    Returns:
        intent: "writing" | "search" | "control" | "feedback" | "chat"
    """
    user_input = state.user_input.strip()
    lowered = user_input.lower()

    # 如果在人类审阅阶段，优先识别为反馈
    if state.phase in ("reviewing", "human_review", "routing_feedback"):
        if any(kw in lowered for kw in _FEEDBACK_KEYWORDS):
            return "feedback"

    # 控制指令
    if any(kw in lowered for kw in _CONTROL_KEYWORDS):
        return "control"

    # 搜索指令
    if any(kw in lowered for kw in _SEARCH_KEYWORDS):
        return "search"

    # 创作指令：包含创作关键词，或像是一个主题
    if any(kw in user_input for kw in _WRITING_KEYWORDS):
        return "writing"

    return "chat"


def entry_node(state: ComedyState) -> dict:
    """入口节点：分类意图并初始化状态。

    Args:
        state: 当前图状态。

    Returns:
        dict: 更新后的 intent 和 phase。
    """
    intent = _classify_intent(state)
    logger.debug("entry_node classify intent: %s for input: %s", intent, state.user_input)

    if intent == "writing":
        return {"intent": intent, "phase": "analyzing"}
    if intent == "chat":
        return {"intent": intent, "phase": "chatting"}
    if intent == "search":
        return {"intent": intent, "phase": "complete"}
    if intent == "control":
        return {"intent": intent, "phase": "complete"}
    if intent == "feedback":
        return {"intent": intent, "phase": "routing_feedback"}

    return {"intent": "chat", "phase": "chatting"}
