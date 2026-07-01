"""润色与建议节点测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from comedy_agent.nodes.polish_node import polish_node
from comedy_agent.nodes.suggest_node import suggest_node
from comedy_agent.state.schema import ComedyState


def test_polish_node_rewrites_section():
    state = ComedyState(
        plan={"outline": ["第一段", "第二段"]},
        current_section=0,
        sections=["用户写的初稿"],
        analysis={"topic": "加班", "attitude": "吐槽", "bias": "老板", "emotion": "愤怒"},
    )
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="润色后的段落")

    result = polish_node(state, llm=mock_llm)

    assert result["phase"] == "human_review"
    assert result["sections"] == ["润色后的段落"]
    assert result["suggestions"] is None
    assert result["feedback"] == ""


def test_polish_node_fallback_on_error():
    state = ComedyState(
        plan={"outline": ["第一段"]},
        current_section=0,
        sections=["初稿"],
    )
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("boom")

    result = polish_node(state, llm=mock_llm)

    assert result["sections"] == ["初稿"]


def test_suggest_node_returns_suggestions():
    state = ComedyState(
        plan={"outline": ["第一段"]},
        current_section=0,
        sections=["用户段落"],
        analysis={"topic": "相亲", "attitude": "自嘲", "bias": "颜值", "emotion": "轻松"},
    )
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="建议1\n建议2")

    result = suggest_node(state, llm=mock_llm)

    assert result["phase"] == "human_review"
    assert "建议1" in result["suggestions"]
    assert result["feedback"] == ""
