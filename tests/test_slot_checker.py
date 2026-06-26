"""SlotCheckingAgent 单元测试。"""

from __future__ import annotations

import pytest

from comedy_agent.agents.slot_checker import SlotCheckingAgent
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def agent():
    return SlotCheckingAgent()


def test_all_slots_filled_moves_to_planning(agent):
    """4 个维度都填满时进入 planning。"""
    result = agent.run(
        ComedyState(
            slots={
                "话题": "通勤",
                "态度": "讽刺",
                "偏见": "无",
                "情绪": "无奈",
            }
        )
    )
    assert result["phase"] == "planning"
    assert result["analysis"] == {
        "topic": "通勤",
        "attitude": "讽刺",
        "bias": "无",
        "emotion": "无奈",
    }


def test_missing_slots_routes_to_consulting(agent):
    """槽位缺失时路由到 consulting，让 GuideAgent 生成 A/B/C。"""
    result = agent.run(
        ComedyState(
            slots={"话题": "通勤"},
        )
    )
    assert result["phase"] == "consulting"
    assert "output" not in result
    assert "response_type" not in result
