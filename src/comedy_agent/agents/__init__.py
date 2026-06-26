"""v4 多 Agent 协作模块。

Phase 2 引入 Supervisor + Worker 架构，所有 Worker 通过
`src/comedy_agent/agents/schemas.py` 中的 Pydantic 模型输出结构化结果。
"""

from __future__ import annotations

from comedy_agent.agents.context_analyzer import ContextAnalyzerAgent
from comedy_agent.agents.intent_classifier import IntentClassifierAgent
from comedy_agent.agents.planner import PlannerAgent
from comedy_agent.agents.reviewer import ReviewerAgent
from comedy_agent.agents.search import SearchAgent
from comedy_agent.agents.supervisor import SupervisorAgent
from comedy_agent.agents.writer import WriterAgent

__all__ = [
    "ContextAnalyzerAgent",
    "IntentClassifierAgent",
    "PlannerAgent",
    "ReviewerAgent",
    "SearchAgent",
    "SupervisorAgent",
    "WriterAgent",
]
