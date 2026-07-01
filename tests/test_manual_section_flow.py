"""样例引导逐段写作（manual_section_mode=True）流程测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langgraph.types import Command

from comedy_agent.agents.schemas import (
    AnalysisResult,
    IntentClassification,
    PlanResult,
    ReviewResult,
)
from comedy_agent.graph.builder import build_graph
from comedy_agent.state.schema import ComedyState
from tests.conftest import make_structured_mock_llm


def _make_analytical_llm() -> MagicMock:
    plain = (
        "todo:\n"
        "1. 分析话题\n"
        "2. 生成大纲\n"
        "3. 逐段写作\n\n"
        "outline:\n"
        "1. 铺垫通勤\n"
        "2. 展开观察\n"
        "3. callback 收尾\n\n"
        "tone: 讽刺"
    )
    return make_structured_mock_llm(
        responses={
            IntentClassification: IntentClassification(intent="writing", confidence=0.95),
            AnalysisResult: AnalysisResult(topic="通勤", attitude="讽刺", bias="无", emotion="无奈"),
            PlanResult: PlanResult(
                todo=["分析", "写作"],
                outline=["铺垫通勤", "展开观察", "callback 收尾"],
                tone="讽刺",
            ),
            ReviewResult: [
                ReviewResult(decision="通过", comments="", score=8),
                ReviewResult(decision="通过", comments="", score=8),
            ],
        },
        plain_content=plain,
    )


def _make_creative_llm() -> MagicMock:
    """example_generator 只需要普通 invoke 返回 JSON 样例。"""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(
        content='{"examples": ["样例1", "样例2", "样例3"]}'
    )
    llm.with_structured_output.return_value.invoke.return_value = MagicMock()
    return llm


def test_manual_section_mode_flow():
    graph = build_graph()
    analytical_llm = _make_analytical_llm()
    creative_llm = _make_creative_llm()
    thread_id = "manual-flow"

    with patch("comedy_agent.nodes.entry_node.ModelFactory") as mock_entry, \
         patch("comedy_agent.nodes.analyze_node.ModelFactory") as mock_analyze, \
         patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_plan, \
         patch("comedy_agent.nodes.example_node.ModelFactory") as mock_example, \
         patch("comedy_agent.nodes.review_node.ModelFactory") as mock_review, \
         patch("comedy_agent.nodes.polish_node.ModelFactory") as mock_polish, \
         patch("comedy_agent.nodes.suggest_node.ModelFactory") as mock_suggest:

        mock_entry.get_model.return_value = analytical_llm
        mock_analyze.get_model.return_value = analytical_llm
        mock_plan.get_model.return_value = analytical_llm
        mock_example.get_model.return_value = creative_llm
        mock_review.get_model.return_value = analytical_llm
        mock_polish.get_model.return_value = creative_llm
        mock_suggest.get_model.return_value = analytical_llm

        result = graph.invoke(
            ComedyState(
                user_input="写一段关于通勤的脱口秀",
                slots={"话题": "通勤", "态度": "讽刺", "偏见": "无", "情绪": "无奈"},
                manual_section_mode=True,
            ),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" in result
        assert "outline" in result["__interrupt__"][0].value

        # 确认计划，进入样例引导写作
        result = graph.invoke(
            Command(resume="开始写作"),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert result["phase"] == "example_review"
        interrupt_value = result["__interrupt__"][0].value
        assert interrupt_value.get("section_examples")
        assert interrupt_value.get("section_goal") == "铺垫通勤"

        # 用户提交第一段（模拟前端残留的 @writer_agent 前缀）
        result = graph.invoke(
            Command(resume="@writer_agent 用户写的第一段"),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert result["phase"] == "human_review"
        assert result["sections"][0] == "用户写的第一段"

        # 通过，进入下一段的样例引导
        result = graph.invoke(
            Command(resume="通过"),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert result["phase"] == "example_review"
        assert result["current_section"] == 1
