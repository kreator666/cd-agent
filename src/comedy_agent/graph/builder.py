"""LangGraph StateGraph 构建器。

Phase 0 构建最简单的 Chat 图：
    START -> chat -> END

后续 Phase 会扩展为带 Supervisor 的星型拓扑。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from comedy_agent.checkpoints.memory import get_memory_saver
from comedy_agent.nodes.chat_node import chat_node
from comedy_agent.state.schema import ComedyState


def build_chat_graph() -> CompiledStateGraph:
    """构建并编译最简 Chat StateGraph。

    Returns:
        已编译的 StateGraph 实例，带 MemorySaver checkpoint。
    """
    builder = StateGraph(ComedyState)
    builder.add_node("chat", chat_node)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)

    checkpointer = get_memory_saver()
    return builder.compile(checkpointer=checkpointer)


class GraphFactory:
    """Compiled graph 单例工厂。"""

    _instance: CompiledStateGraph | None = None

    @classmethod
    def get(cls) -> CompiledStateGraph:
        """获取全局唯一的编译后 Chat Graph。"""
        if cls._instance is None:
            cls._instance = build_chat_graph()
        return cls._instance


def get_chat_graph() -> CompiledStateGraph:
    """获取编译后的 Chat Graph。"""
    return GraphFactory.get()
