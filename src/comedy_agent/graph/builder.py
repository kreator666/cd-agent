"""LangGraph StateGraph 构建器。

Phase 1 构建完整的创作状态机：
    entry → analyze → plan → write → review → human → process_feedback
              ↑                                      ↓
              └──────── 修改/重写 ───────────────────┘
                                                              ↓
                                                        finalize → END

入口同时支持普通 chat 路径：
    entry → chat → END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from comedy_agent.checkpoints.memory import get_memory_saver
from comedy_agent.graph import edges
from comedy_agent.nodes import (
    analyze_node,
    chat_node,
    entry_node,
    finalize_node,
    human_node,
    plan_node,
    process_feedback_node,
    review_node,
    write_node,
)
from comedy_agent.state.schema import ComedyState


def build_graph() -> CompiledStateGraph:
    """构建并编译完整创作状态 StateGraph。

    Returns:
        已编译的 StateGraph 实例，带 MemorySaver checkpoint。
    """
    builder = StateGraph(ComedyState)

    # 注册节点
    builder.add_node("entry", entry_node)
    builder.add_node("chat", chat_node)
    builder.add_node("analyze", analyze_node)
    builder.add_node("plan", plan_node)
    builder.add_node("write", write_node)
    builder.add_node("review", review_node)
    builder.add_node("human", human_node)
    builder.add_node("process_feedback", process_feedback_node)
    builder.add_node("finalize", finalize_node)

    # 入口与条件边
    builder.add_edge(START, "entry")
    builder.add_conditional_edges("entry", edges.route_entry)

    # 创作主链路
    builder.add_conditional_edges("analyze", edges.route_after_analyze)
    builder.add_conditional_edges("plan", edges.route_after_plan)
    builder.add_conditional_edges("write", edges.route_after_write)
    builder.add_conditional_edges("review", edges.route_after_review)
    builder.add_conditional_edges("human", edges.route_after_human)
    builder.add_conditional_edges("process_feedback", edges.route_after_feedback)

    # 聊天与收尾直连 END
    builder.add_conditional_edges("chat", edges.route_after_chat)
    builder.add_conditional_edges("finalize", edges.route_after_finalize)

    checkpointer = get_memory_saver()
    return builder.compile(checkpointer=checkpointer)


# 保留 Phase 0 的函数名，供 api/server.py 兼容导入
def build_chat_graph() -> CompiledStateGraph:
    """``build_graph`` 的别名，保持向后兼容。"""
    return build_graph()


class GraphFactory:
    """Compiled graph 单例工厂。"""

    _instance: CompiledStateGraph | None = None

    @classmethod
    def get(cls) -> CompiledStateGraph:
        """获取全局唯一的编译后 Graph。"""
        if cls._instance is None:
            cls._instance = build_graph()
        return cls._instance


def get_chat_graph() -> CompiledStateGraph:
    """获取编译后的 Graph。"""
    return GraphFactory.get()
