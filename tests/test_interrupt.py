"""v4 Human-in-the-Loop 中断恢复测试（Supervisor 图）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langgraph.types import Command

from comedy_agent.agents.schemas import (
    AnalysisResult,
    IntentClassification,
    PlanResult,
    ReviewResult,
    UserIntent,
)
from comedy_agent.graph.builder import build_graph
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def graph():
    """提供编译后的 Supervisor StateGraph。"""
    return build_graph()


def _make_analytical_llm() -> MagicMock:
    """分析类 Worker 的 mock LLM。"""
    from tests.conftest import make_structured_mock_llm

    return make_structured_mock_llm(
        responses={
            IntentClassification: IntentClassification(
                intent=UserIntent.WRITING, confidence=0.95
            ),
            AnalysisResult: AnalysisResult(
                topic="通勤", attitude="讽刺", bias="无", emotion="无奈"
            ),
            PlanResult: PlanResult(
                todo=["分析", "写作"],
                outline=["铺垫通勤", "展开观察", "callback 收尾"],
                tone="讽刺",
            ),
            ReviewResult: ReviewResult(
                decision="修改", comments="再犀利一点", score=7
            ),
        }
    )


def _make_creative_llm(section_texts: list[str]) -> MagicMock:
    """写作 Worker 的 mock LLM。"""
    llm = MagicMock()
    llm.invoke.side_effect = [MagicMock(content=text) for text in section_texts]
    llm.with_structured_output.return_value.invoke.return_value = MagicMock()
    return llm


def test_interrupt_pauses_at_human_node(graph):
    """创作流程在 human_node 暂停并返回 interrupt。"""
    analytical_llm = _make_analytical_llm()
    creative_llm = _make_creative_llm(["第一段内容"])

    with patch("comedy_agent.nodes.entry_node.ModelFactory") as mock_entry, \
         patch("comedy_agent.nodes.analyze_node.ModelFactory") as mock_analyze, \
         patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_plan, \
         patch("comedy_agent.nodes.write_node.ModelFactory") as mock_write, \
         patch("comedy_agent.nodes.review_node.ModelFactory") as mock_review:

        mock_entry.get_model.return_value = analytical_llm
        mock_analyze.get_model.return_value = analytical_llm
        mock_plan.get_model.return_value = analytical_llm
        mock_write.get_model.return_value = creative_llm
        mock_review.get_model.return_value = analytical_llm

        result = graph.invoke(
            ComedyState(user_input="写一段关于通勤的脱口秀", slots={"话题": "通勤", "态度": "讽刺", "偏见": "无", "情绪": "无奈"}),
            config={"configurable": {"thread_id": "int-pause"}},
        )

    assert "__interrupt__" in result
    interrupt_value = result["__interrupt__"][0].value
    assert interrupt_value["message"] == "请审阅当前段落并提供反馈"
    assert interrupt_value["section_text"] == "第一段内容"


def test_resume_with_approve_feedback(graph):
    """恢复 interrupt：用户输入'通过'，继续创作或收尾。"""
    analytical_llm = _make_analytical_llm()
    creative_llm = _make_creative_llm(["第一段内容", "第二段内容", "第三段内容"])

    with patch("comedy_agent.nodes.entry_node.ModelFactory") as mock_entry, \
         patch("comedy_agent.nodes.analyze_node.ModelFactory") as mock_analyze, \
         patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_plan, \
         patch("comedy_agent.nodes.write_node.ModelFactory") as mock_write, \
         patch("comedy_agent.nodes.review_node.ModelFactory") as mock_review:

        mock_entry.get_model.return_value = analytical_llm
        mock_analyze.get_model.return_value = analytical_llm
        mock_plan.get_model.return_value = analytical_llm
        mock_write.get_model.return_value = creative_llm
        mock_review.get_model.return_value = analytical_llm

        thread_id = "int-approve"

        result = graph.invoke(
            ComedyState(user_input="写一段关于通勤的脱口秀", slots={"话题": "通勤", "态度": "讽刺", "偏见": "无", "情绪": "无奈"}),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" in result

        result = graph.invoke(
            Command(resume="通过"),
            config={"configurable": {"thread_id": thread_id}},
        )

    assert "phase" in result
    # 由于 outline 有 3 段，继续执行后应再次 interrupt 或完成
    final_state = ComedyState.model_validate(result)
    assert final_state.phase in ("human_review", "complete")


def test_resume_with_modify_feedback(graph):
    """恢复 interrupt：用户输入修改意见，重写当前段并再次暂停。"""
    analytical_llm = _make_analytical_llm()
    first_draft = "加班加到手机都没电了。"
    revised_draft = "加班加到手机都没电了，但我还在回老板消息。"
    creative_llm = _make_creative_llm([first_draft, revised_draft])

    with patch("comedy_agent.nodes.entry_node.ModelFactory") as mock_entry, \
         patch("comedy_agent.nodes.analyze_node.ModelFactory") as mock_analyze, \
         patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_plan, \
         patch("comedy_agent.nodes.write_node.ModelFactory") as mock_write, \
         patch("comedy_agent.nodes.review_node.ModelFactory") as mock_review:

        mock_entry.get_model.return_value = analytical_llm
        mock_analyze.get_model.return_value = analytical_llm
        mock_plan.get_model.return_value = analytical_llm
        mock_write.get_model.return_value = creative_llm
        mock_review.get_model.return_value = analytical_llm

        thread_id = "int-modify"

        result = graph.invoke(
            ComedyState(user_input="写一段关于加班的脱口秀", slots={"话题": "加班", "态度": "自嘲", "偏见": "无", "情绪": "疲惫"}),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" in result
        assert result["__interrupt__"][0].value["section_text"] == first_draft

        result = graph.invoke(
            Command(resume="这里再讽刺一点"),
            config={"configurable": {"thread_id": thread_id}},
        )

    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value["section_text"] == revised_draft
