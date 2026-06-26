"""条件边函数集合。

所有阶段切换由代码条件边决定，模型只负责内容生成。
"""

from __future__ import annotations

from typing import Literal

from comedy_agent.state.schema import ComedyState


def route_entry(state: ComedyState) -> Literal["analyze", "chat", "finalize"]:
    """入口路由：根据意图选择下一步。

    Args:
        state: 当前图状态。

    Returns:
        next node name
    """
    intent = state.intent
    if intent == "writing":
        return "analyze"
    if intent == "chat":
        return "chat"
    # search / control / feedback 等暂直接收尾，后续 Phase 扩展
    return "finalize"


def route_after_analyze(state: ComedyState) -> Literal["plan"]:
    """分析后路由。"""
    return "plan"


def route_after_plan(state: ComedyState) -> Literal["write"]:
    """计划后路由。"""
    return "write"


def route_after_write(state: ComedyState) -> Literal["review"]:
    """写作后路由。"""
    return "review"


def route_after_review(state: ComedyState) -> Literal["human"]:
    """审核后路由。"""
    return "human"


def route_after_human(state: ComedyState) -> Literal["process_feedback"]:
    """人类审阅后路由。"""
    return "process_feedback"


def route_after_feedback(
    state: ComedyState,
) -> Literal["write", "plan", "finalize"]:
    """反馈处理后路由：根据 phase 决定下一步。

    Args:
        state: 当前图状态。

    Returns:
        next node name
    """
    phase = state.phase
    if phase == "finalizing":
        return "finalize"
    if phase == "planning":
        return "plan"
    return "write"


def route_after_chat(state: ComedyState) -> Literal["__end__"]:
    """聊天后路由。"""
    return "__end__"


def route_after_finalize(state: ComedyState) -> Literal["__end__"]:
    """收尾后路由。"""
    return "__end__"
