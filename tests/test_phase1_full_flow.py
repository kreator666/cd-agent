"""Phase 1→2 端到端验收测试。

验证 Supervisor 调度下的状态机仍能完成
“输入主题 → 分析 → 计划 → 逐段写作 → 人类审阅 → 反馈恢复 → 最终输出”。
"""

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
                outline=["铺垫通勤烦恼", "展开观察", "callback 收尾"],
                tone="讽刺",
            ),
            ReviewResult: ReviewResult(
                decision="修改", comments="再犀利一点", score=7
            ),
        },
        plain_content=(
            "todo:\n"
            "1. 分析话题\n"
            "2. 生成大纲\n"
            "3. 逐段写作\n\n"
            "outline:\n"
            "1. 铺垫通勤烦恼\n"
            "2. 展开观察\n"
            "3. callback 收尾\n\n"
            "tone: 讽刺"
        ),
    )


def _make_creative_llm(section_texts: list[str]) -> MagicMock:
    """写作 Worker 的 mock LLM。"""
    llm = MagicMock()
    llm.invoke.side_effect = [MagicMock(content=text) for text in section_texts]
    llm.with_structured_output.return_value.invoke.return_value = MagicMock()
    return llm


def test_full_writing_flow_with_human_in_the_loop(graph):
    """完整创作流程：3 段 outline，逐段通过，最终输出完整文本。"""
    thread_id = "phase1-full-flow"

    analytical_llm = _make_analytical_llm()
    section_texts = [
        "每天早上挤地铁，我都觉得自己像一块被压扁的吐司。",
        "旁边大哥的胳肢窝贴着我脸，我突然理解了什么是‘贴脸开大’。",
        "所以通勤的真正意义，是让你到公司时已经经历了一轮社会的毒打。",
    ]
    creative_llm = _make_creative_llm(section_texts)

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
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" in result
        assert "outline" in result["__interrupt__"][0].value

        result = graph.invoke(
            Command(resume="开始写作"),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" in result
        interrupt = result["__interrupt__"][0].value
        assert interrupt["section_text"] == section_texts[0]

        for expected_text in section_texts[1:]:
            result = graph.invoke(
                Command(resume="通过"),
                config={"configurable": {"thread_id": thread_id}},
            )
            assert "__interrupt__" in result
            interrupt = result["__interrupt__"][0].value
            assert interrupt["section_text"] == expected_text

        result = graph.invoke(
            Command(resume="通过"),
            config={"configurable": {"thread_id": thread_id}},
        )

    final_state = ComedyState.model_validate(result)
    assert final_state.phase == "complete"
    assert final_state.output
    for text in section_texts:
        assert text in final_state.output


def test_modify_feedback_rewrites_current_section(graph):
    """用户给出修改意见后，当前段落应被重写并再次暂停等待反馈。"""
    thread_id = "phase1-modify"

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

        result = graph.invoke(
            ComedyState(user_input="写一段关于加班的脱口秀", slots={"话题": "加班", "态度": "自嘲", "偏见": "无", "情绪": "疲惫"}),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" in result
        assert "outline" in result["__interrupt__"][0].value

        result = graph.invoke(
            Command(resume="开始写作"),
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
