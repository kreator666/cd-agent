"""LangGraph StateGraph 构建器兼容入口。

Phase 2 起，默认图已迁移为 Supervisor 星型拓扑，
本文件仅做转发，保留 ``build_graph`` / ``build_chat_graph`` 等旧入口。
"""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from comedy_agent.checkpoints.memory import get_memory_saver
from comedy_agent.graph.supervisor_graph import build_supervisor_graph


def build_graph() -> CompiledStateGraph:
    """构建并编译完整创作 StateGraph（Supervisor 星型拓扑）。"""
    return build_supervisor_graph()


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
