"""Supervisor 星型拓扑图构建器。

Phase 2 将线性状态机改为 Supervisor + Worker 星型拓扑：
所有 Worker 执行完后回到 Supervisor，由 Supervisor 根据 ``phase`` 决定下一步。

拓扑示意：

    START -> supervisor
    supervisor -> conditional_edges -> workers / human / process_feedback / finalize / END
    workers -> supervisor
    human -> process_feedback -> supervisor
    finalize -> END
    chat -> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from comedy_agent.agents.supervisor import SupervisorAgent
from comedy_agent.checkpoints.memory import get_memory_saver
from comedy_agent.nodes import (
    analyze_node,
    chat_node,
    entry_node,
    finalize_node,
    guide_node,
    human_node,
    plan_node,
    process_feedback_node,
    review_node,
    search_node,
    slot_checker_node,
    slot_filler_node,
    write_node,
)
from comedy_agent.state.schema import ComedyState

# Worker 节点名与节点函数的映射
WORKER_NODES = {
    "intent_classifier": entry_node,
    "slot_filler": slot_filler_node,
    "slot_checker": slot_checker_node,
    "guide": guide_node,
    "context_analyzer": analyze_node,
    "planner": plan_node,
    "writer": write_node,
    "reviewer": review_node,
    "search": search_node,
    "chat": chat_node,
}


def build_supervisor_graph() -> CompiledStateGraph:
    """构建 Supervisor 星型拓扑 StateGraph。

    Returns:
        已编译的 StateGraph 实例，带 MemorySaver checkpoint。
    """
    builder = StateGraph(ComedyState)
    supervisor = SupervisorAgent()

    # 注册 Supervisor
    builder.add_node("supervisor", supervisor.run)

    # 注册 Worker 节点
    for name, node_fn in WORKER_NODES.items():
        builder.add_node(name, node_fn)

    # 注册 HITL 与收尾节点
    builder.add_node("human", human_node)
    builder.add_node("process_feedback", process_feedback_node)
    builder.add_node("finalize", finalize_node)

    # 入口：START -> supervisor
    builder.add_edge(START, "supervisor")

    # Supervisor 条件边：根据状态派发 Worker 或结束
    builder.add_conditional_edges(
        "supervisor",
        supervisor.route,
        {
            "intent_classifier": "intent_classifier",
            "slot_filler": "slot_filler",
            "slot_checker": "slot_checker",
            "guide": "guide",
            "context_analyzer": "context_analyzer",
            "planner": "planner",
            "writer": "writer",
            "reviewer": "reviewer",
            "search": "search",
            "chat": "chat",
            "human": "human",
            "process_feedback": "process_feedback",
            "finalize": "finalize",
            "__end__": END,
        },
    )

    # Worker 执行完后回到 Supervisor
    for name in WORKER_NODES:
        if name == "chat":
            # chat 直接结束，不再回到 supervisor（减少一次空转）
            continue
        builder.add_edge(name, "supervisor")

    # chat 与 finalize 直连 END
    builder.add_edge("chat", END)
    builder.add_edge("finalize", END)

    # 人类审阅链路：human -> process_feedback -> supervisor
    builder.add_edge("human", "process_feedback")
    builder.add_edge("process_feedback", "supervisor")

    checkpointer = get_memory_saver()
    return builder.compile(checkpointer=checkpointer)
