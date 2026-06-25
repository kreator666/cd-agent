"""全局应用状态。

持有 Orchestrator、LangGraph 与 Memory 实例，供 API 层各模块共享。
"""

from __future__ import annotations

from typing import Any

from langgraph.graph.state import CompiledStateGraph


class AppState:
    """全局应用状态。"""

    def __init__(self) -> None:
        self.orch: Any | None = None
        self.graph: CompiledStateGraph | None = None
        self.memory: Any | None = None
        self.start_time: float | None = None


state = AppState()
