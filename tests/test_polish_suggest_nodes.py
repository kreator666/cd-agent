"""润色与建议节点测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from comedy_agent.core.config import settings
from comedy_agent.models.factory import ModelConfigError
from comedy_agent.nodes.polish_node import polish_node
from comedy_agent.nodes.process_feedback_node import process_feedback_node
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


def test_suggest_node_returns_suggestions_and_revision():
    state = ComedyState(
        plan={"outline": ["第一段"]},
        current_section=0,
        sections=["用户段落"],
        analysis={"topic": "相亲", "attitude": "自嘲", "bias": "颜值", "emotion": "轻松"},
    )
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content="💡 改进建议：\n- 建议1\n- 建议2\n\n✏️ 建议修改版：\n修改后的用户段落"
    )

    result = suggest_node(state, llm=mock_llm)

    assert result["phase"] == "human_review"
    assert "建议1" in result["suggestions"]
    assert "💡" not in result["suggestions"]
    assert result["suggested_revision"] == "修改后的用户段落"
    assert result["feedback"] == ""


def test_suggest_node_falls_back_when_no_revision_marker():
    """如果模型没按格式输出建议修改版，则全部内容作为 suggestions，revision 为空。"""
    state = ComedyState(
        plan={"outline": ["第一段"]},
        current_section=0,
        sections=["用户段落"],
        analysis={"topic": "相亲", "attitude": "自嘲", "bias": "颜值", "emotion": "轻松"},
    )
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="只有建议，没有修改版")

    result = suggest_node(state, llm=mock_llm)

    assert result["phase"] == "human_review"
    assert "只有建议" in result["suggestions"]
    assert result["suggested_revision"] == ""


def test_polish_node_uses_same_model_as_writer():
    """当 model 为空但 model_used 已记录时，润色应使用生成时相同的模型。"""
    state = ComedyState(
        plan={"outline": ["第一段"]},
        current_section=0,
        sections=["初稿"],
        model_used="gpt-4o",
    )
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="润色后")

    with patch("comedy_agent.nodes.polish_node.ModelFactory") as mock_factory:
        mock_factory.get_model.return_value = mock_llm
        result = polish_node(state)

    mock_factory.get_model.assert_called_once_with("gpt-4o", task_type="creative")
    assert result["sections"] == ["润色后"]


def test_polish_node_prefers_explicit_model_over_model_used():
    """当用户显式指定 model 时，润色优先使用该模型。"""
    state = ComedyState(
        plan={"outline": ["第一段"]},
        current_section=0,
        sections=["初稿"],
        model="qwen-max",
        model_used="gpt-4o",
    )
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="润色后")

    with patch("comedy_agent.nodes.polish_node.ModelFactory") as mock_factory:
        mock_factory.get_model.return_value = mock_llm
        result = polish_node(state)

    mock_factory.get_model.assert_called_once_with("qwen-max", task_type="creative")
    assert result["sections"] == ["润色后"]


def test_process_feedback_adopt_revision():
    """点击“采纳建议版”后，当前段落应替换为 suggested_revision 并回到 human_review。"""
    state = ComedyState(
        plan={"outline": ["第一段", "第二段"]},
        current_section=0,
        sections=["原文段落"],
        feedback="采纳建议版",
        suggested_revision="建议修改后的段落",
    )

    result = process_feedback_node(state)

    assert result["phase"] == "human_review"
    assert result["sections"] == ["建议修改后的段落"]
    assert result["current_section"] == 0
    assert result["suggestions"] is None
    assert result["suggested_revision"] is None
    assert result["feedback"] == ""


def test_polish_node_falls_back_to_default_when_model_unavailable():
    """当首选模型不可用时，润色应回退到默认模型而不是崩溃。"""
    state = ComedyState(
        plan={"outline": ["第一段"]},
        current_section=0,
        sections=["初稿"],
        model_used="claude-3-5-sonnet",
    )
    fallback_llm = MagicMock()
    fallback_llm.invoke.return_value = MagicMock(content="默认模型润色")

    with patch("comedy_agent.nodes.polish_node.ModelFactory") as mock_factory:
        mock_factory.get_model.side_effect = [
            ModelConfigError("no key"),
            fallback_llm,
        ]
        result = polish_node(state)

    assert mock_factory.get_model.call_count == 2
    first_call = mock_factory.get_model.call_args_list[0]
    second_call = mock_factory.get_model.call_args_list[1]
    assert first_call.kwargs.get("task_type") == "creative"
    # 回退时使用默认模型，不再带 task_type
    assert second_call.args[0] == settings.default_model
    assert "task_type" not in second_call.kwargs
    assert result["sections"] == ["默认模型润色"]
