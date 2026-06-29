"""SlotCheckingAgent 单元测试。"""

from __future__ import annotations

import pytest

from comedy_agent.agents.slot_checker import SlotCheckingAgent
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def agent():
    return SlotCheckingAgent()


def test_all_slots_filled_moves_to_analyzing(agent):
    """4 个维度都填满时进入 analyzing，由 Context Analyzer 生成 analysis。"""
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
    assert result["phase"] == "analyzing"
    assert "analysis" not in result


def test_missing_slots_routes_to_consulting(agent):
    """槽位缺失且信息不足时路由到 consulting，让 GuideAgent 生成 A/B/C。"""
    result = agent.run(
        ComedyState(
            slots={"话题": "通勤"},
        )
    )
    assert result["phase"] == "consulting"
    assert "output" not in result
    assert "response_type" not in result


def test_missing_slots_but_enough_user_turns_moves_to_analyzing(agent):
    """槽位未填满，但用户已聊够轮数，也进入 analyzing。"""
    from langchain_core.messages import HumanMessage

    result = agent.run(
        ComedyState(
            slots={"话题": "通勤"},
            messages=[
                HumanMessage(content="我想写通勤"),
                HumanMessage(content="态度讽刺"),
                HumanMessage(content="情绪无奈"),
            ],
        )
    )
    assert result["phase"] == "analyzing"


def test_trigger_keyword_moves_to_analyzing(agent):
    """用户明确说「开始创作」等触发词时进入 analyzing。"""
    result = agent.run(
        ComedyState(
            slots={"话题": "通勤"},
            user_input="开始创作",
        )
    )
    assert result["phase"] == "analyzing"
