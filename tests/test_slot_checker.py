"""SlotCheckingAgent 单元测试。"""

from __future__ import annotations

import pytest

from comedy_agent.agents.slot_checker import SlotCheckingAgent
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def agent():
    return SlotCheckingAgent()


def test_all_slots_filled_without_confirmation_routes_to_consulting(agent):
    """4 个维度都填满但用户未确认时，先进入 consulting 由 GuideAgent 询问是否满意。"""
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
    assert result["phase"] == "consulting"
    assert "analysis" not in result


def test_all_slots_filled_with_confirmation_moves_to_analyzing(agent):
    """4 个维度都填满且用户确认「生成大纲」时进入 analyzing。"""
    result = agent.run(
        ComedyState(
            slots={
                "话题": "通勤",
                "态度": "讽刺",
                "偏见": "无",
                "情绪": "无奈",
            },
            user_input="确认满意，生成大纲",
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


def test_missing_slots_with_many_turns_stays_consulting(agent):
    """槽位未填满且没有触发词时，即使对话轮数多也仍保持 consulting。"""
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
    assert result["phase"] == "consulting"


def test_trigger_keyword_moves_to_analyzing(agent):
    """用户明确说「开始创作」等触发词时进入 analyzing。"""
    result = agent.run(
        ComedyState(
            slots={"话题": "通勤"},
            user_input="开始创作",
        )
    )
    assert result["phase"] == "analyzing"
