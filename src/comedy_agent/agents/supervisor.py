"""Supervisor Worker。

负责检查全局状态并决定下一步派发到哪个 Worker。
所有 Worker 执行完后回到 Supervisor，由 Supervisor 根据 ``phase`` 路由。
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

# Worker 名称列表（与 graph/supervisor_graph.py 中注册的节点名一致）
MEMBERS = [
    "intent_classifier",
    "slot_filler",
    "slot_checker",
    "guide",
    "context_analyzer",
    "planner",
    "writer",
    "example_generator",
    "example_review",
    "draft_node",
    "reviewer",
    "search",
    "chat",
]

# Supervisor 可返回的下一个目标
NextNode = Literal[
    "intent_classifier",
    "slot_filler",
    "slot_checker",
    "guide",
    "context_analyzer",
    "planner",
    "plan_review",
    "process_plan_feedback",
    "writer",
    "example_generator",
    "example_review",
    "draft_node",
    "reviewer",
    "search",
    "chat",
    "human",
    "process_feedback",
    "finalize",
    "__end__",
]


class SupervisorAgent:
    """Supervisor Agent：纯代码条件路由，模型不决定流程。"""

    def run(self, state: ComedyState) -> dict[str, Any]:
        """Supervisor 节点函数（可为空操作，仅用于图拓扑）。"""
        logger.debug("supervisor: current phase=%s", state.phase)
        return {}

    def route(self, state: ComedyState) -> NextNode:
        """根据当前状态决定下一个节点。

        Args:
            state: 当前图状态。

        Returns:
            下一个节点名称，或 ``__end__`` 结束流程。
        """
        phase = state.phase

        if phase == "idle":
            return "intent_classifier"

        if phase == "filling_slots":
            return "slot_filler"

        if phase == "slot_checking":
            return "slot_checker"

        if phase == "analyzing":
            return "context_analyzer"

        if phase == "planning":
            return "planner"

        if phase == "plan_review":
            return "plan_review"

        if phase == "routing_plan_feedback":
            return "process_plan_feedback"

        if phase == "writing":
            return "example_generator" if state.manual_section_mode else "writer"

        if phase == "generating_examples":
            return "example_generator"

        if phase == "example_review":
            return "example_review"

        if phase == "drafting":
            return "draft_node"

        if phase == "reviewing":
            return "reviewer"

        if phase == "human_review":
            return "human"

        if phase == "routing_feedback":
            return "process_feedback"

        if phase == "searching":
            return "search"

        if phase == "chatting":
            return "chat"

        if phase == "consulting":
            return "guide"

        if phase == "finalizing":
            return "finalize"

        if phase == "complete":
            return "__end__"

        # 未知 phase 兜底：直接结束，避免死循环
        logger.warning("supervisor: unknown phase '%s', ending", phase)
        return "__end__"
