"""Supervisor Agent 单元测试。"""

from __future__ import annotations

import pytest

from comedy_agent.agents.supervisor import SupervisorAgent
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def supervisor():
    return SupervisorAgent()


@pytest.mark.parametrize(
    "phase,expected",
    [
        ("idle", "intent_classifier"),
        ("filling_slots", "slot_filler"),
        ("slot_checking", "slot_checker"),
        ("analyzing", "context_analyzer"),
        ("planning", "planner"),
        ("writing", "writer"),
        ("reviewing", "reviewer"),
        ("human_review", "human"),
        ("routing_feedback", "process_feedback"),
        ("searching", "search"),
        ("chatting", "chat"),
        ("consulting", "guide"),
        ("finalizing", "finalize"),
        ("complete", "__end__"),
    ],
)
def test_supervisor_route(supervisor, phase, expected):
    assert supervisor.route(ComedyState(phase=phase)) == expected


def test_supervisor_run_is_noop(supervisor):
    """Supervisor 节点函数本身不修改状态。"""
    assert supervisor.run(ComedyState()) == {}
