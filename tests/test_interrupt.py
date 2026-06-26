"""v4 Human-in-the-Loop 中断恢复测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langgraph.types import Command

from comedy_agent.graph.builder import build_graph
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def graph():
    """提供编译后的状态机 Graph。"""
    return build_graph()


@pytest.fixture
def mock_llm():
    """提供统一 mock LLM。"""
    llm = MagicMock()
    llm.invoke = MagicMock(return_value=MagicMock(content="mocked llm response"))
    return llm


def _setup_writing_mocks(mock_llm):
    """统一 patch 创作链路各节点的 ModelFactory。"""
    return [
        patch("comedy_agent.nodes.analyze_node.ModelFactory", return_value=mock_llm),
        patch("comedy_agent.nodes.plan_node.ModelFactory", return_value=mock_llm),
        patch("comedy_agent.nodes.write_node.ModelFactory", return_value=mock_llm),
        patch("comedy_agent.nodes.review_node.ModelFactory", return_value=mock_llm),
    ]


def test_interrupt_pauses_at_human_node(graph, mock_llm):
    """创作流程在 human_node 暂停并返回 interrupt。"""
    with patch("comedy_agent.nodes.analyze_node.ModelFactory") as mock_analyze, \
         patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_plan, \
         patch("comedy_agent.nodes.write_node.ModelFactory") as mock_write, \
         patch("comedy_agent.nodes.review_node.ModelFactory") as mock_review:

        mock_analyze.get_model.return_value = mock_llm
        mock_plan.get_model.return_value = mock_llm
        mock_write.get_model.return_value = mock_llm
        mock_review.get_model.return_value = mock_llm

        result = graph.invoke(
            ComedyState(user_input="写一段关于通勤的脱口秀"),
            config={"configurable": {"thread_id": "int-pause"}},
        )

    assert "__interrupt__" in result
    interrupt_value = result["__interrupt__"][0].value
    assert interrupt_value["message"] == "请审阅当前段落并提供反馈"


def test_resume_with_approve_feedback(graph, mock_llm):
    """恢复 interrupt：用户输入"通过"，进入下一段或收尾。"""
    with patch("comedy_agent.nodes.analyze_node.ModelFactory") as mock_analyze, \
         patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_plan, \
         patch("comedy_agent.nodes.write_node.ModelFactory") as mock_write, \
         patch("comedy_agent.nodes.review_node.ModelFactory") as mock_review:

        mock_analyze.get_model.return_value = mock_llm
        mock_plan.get_model.return_value = mock_llm
        mock_write.get_model.return_value = mock_llm
        mock_review.get_model.return_value = mock_llm

        thread_id = "int-approve"

        # 第一次调用触发 interrupt
        result = graph.invoke(
            ComedyState(user_input="写一段关于通勤的脱口秀"),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" in result

        # 恢复：用户输入"通过"
        result = graph.invoke(
            Command(resume="通过"),
            config={"configurable": {"thread_id": thread_id}},
        )

    # 应该继续执行直到下一个 interrupt 或 complete
    # 由于 outline 由 mock 生成，结果可能再次 interrupt 或 finalize
    assert "phase" in result


def test_resume_with_modify_feedback(graph, mock_llm):
    """恢复 interrupt：用户输入修改意见，重写当前段。"""
    with patch("comedy_agent.nodes.analyze_node.ModelFactory") as mock_analyze, \
         patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_plan, \
         patch("comedy_agent.nodes.write_node.ModelFactory") as mock_write, \
         patch("comedy_agent.nodes.review_node.ModelFactory") as mock_review:

        mock_analyze.get_model.return_value = mock_llm
        mock_plan.get_model.return_value = mock_llm
        mock_write.get_model.return_value = mock_llm
        mock_review.get_model.return_value = mock_llm

        thread_id = "int-modify"

        result = graph.invoke(
            ComedyState(user_input="写一段关于通勤的脱口秀"),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" in result

        # 恢复：用户输入修改意见
        result = graph.invoke(
            Command(resume="这里再讽刺一点"),
            config={"configurable": {"thread_id": thread_id}},
        )

    # 修改后应再次触发 interrupt 等待反馈
    assert "__interrupt__" in result
