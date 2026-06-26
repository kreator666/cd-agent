"""v4 核心状态机单元测试。

验证所有条件边分支和阶段流转。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.graph import edges
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
    llm.invoke = MagicMock(
        return_value=MagicMock(content="mocked llm response")
    )
    return llm


class TestEdges:
    """条件边单元测试。"""

    def test_route_entry_writing(self):
        state = ComedyState(intent="writing")
        assert edges.route_entry(state) == "analyze"

    def test_route_entry_chat(self):
        state = ComedyState(intent="chat")
        assert edges.route_entry(state) == "chat"

    def test_route_entry_default(self):
        state = ComedyState(intent="search")
        assert edges.route_entry(state) == "finalize"

    def test_route_after_feedback_finalize(self):
        state = ComedyState(phase="finalizing")
        assert edges.route_after_feedback(state) == "finalize"

    def test_route_after_feedback_plan(self):
        state = ComedyState(phase="planning")
        assert edges.route_after_feedback(state) == "plan"

    def test_route_after_feedback_write(self):
        state = ComedyState(phase="writing")
        assert edges.route_after_feedback(state) == "write"


class TestStateMachineFlow:
    """完整状态机流程测试（LLM 全部 mock）。"""

    def test_chat_path(self, graph, mock_llm):
        """普通聊天路径：entry → chat → END。"""
        with patch("comedy_agent.nodes.chat_node.ModelFactory") as mock_factory:
            mock_factory.get_model.return_value = mock_llm

            result = graph.invoke(
                ComedyState(user_input="你好"),
                config={"configurable": {"thread_id": "sm-chat"}},
            )

        state = ComedyState.model_validate(result)
        assert state.phase == "complete"
        assert state.intent == "chat"

    def test_writing_path_to_interrupt(self, graph, mock_llm):
        """创作路径直到触发 interrupt。"""
        # analyze / plan / write / review 都需要 LLM
        with patch("comedy_agent.nodes.analyze_node.ModelFactory") as mock_analyze, \
             patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_plan, \
             patch("comedy_agent.nodes.write_node.ModelFactory") as mock_write, \
             patch("comedy_agent.nodes.review_node.ModelFactory") as mock_review:

            mock_analyze.get_model.return_value = mock_llm
            mock_plan.get_model.return_value = mock_llm
            mock_write.get_model.return_value = mock_llm
            mock_review.get_model.return_value = mock_llm

            result = graph.invoke(
                ComedyState(user_input="写一段关于加班的脱口秀"),
                config={"configurable": {"thread_id": "sm-writing"}},
            )

        assert "__interrupt__" in result
        interrupt_value = result["__interrupt__"][0].value
        assert "section_text" in interrupt_value

    def test_plan_shape(self, graph, mock_llm):
        """验证 plan_node 生成的 plan 包含必要字段。"""
        from comedy_agent.nodes.plan_node import plan_node

        with patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_factory:
            mock_llm.invoke = MagicMock(
                return_value=MagicMock(
                    content='{"todo": ["t1"], "outline": ["o1", "o2", "o3"], "tone": "讽刺"}'
                )
            )
            mock_factory.get_model.return_value = mock_llm

            result = plan_node(
                ComedyState(
                    user_input="写一段关于加班的脱口秀",
                    analysis={
                        "topic": "加班",
                        "attitude": "讽刺",
                        "bias": "无",
                        "emotion": "无奈",
                    },
                )
            )

        assert result["plan"]["todo"] == ["t1"]
        assert result["plan"]["outline"] == ["o1", "o2", "o3"]
        assert result["phase"] == "writing"
