"""v4 Supervisor 状态机测试。

验证 Supervisor 路由表与星型拓扑下的完整流程。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.agents.schemas import (
    AnalysisResult,
    IntentClassification,
    PlanResult,
    ReviewResult,
    UserIntent,
)
from comedy_agent.agents.supervisor import SupervisorAgent
from comedy_agent.graph.builder import build_graph
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def graph():
    """提供编译后的 Supervisor StateGraph。"""
    return build_graph()


@pytest.fixture
def supervisor():
    """提供 SupervisorAgent 实例。"""
    return SupervisorAgent()


class TestSupervisorRouting:
    """Supervisor 条件路由单元测试。"""

    def test_route_idle_to_intent_classifier(self, supervisor):
        assert supervisor.route(ComedyState(phase="idle")) == "intent_classifier"

    def test_route_analyzing_to_context_analyzer(self, supervisor):
        assert supervisor.route(ComedyState(phase="analyzing")) == "context_analyzer"

    def test_route_planning_to_planner(self, supervisor):
        assert supervisor.route(ComedyState(phase="planning")) == "planner"

    def test_route_writing_to_writer(self, supervisor):
        assert supervisor.route(ComedyState(phase="writing")) == "writer"

    def test_route_reviewing_to_reviewer(self, supervisor):
        assert supervisor.route(ComedyState(phase="reviewing")) == "reviewer"

    def test_route_human_review_to_human(self, supervisor):
        assert supervisor.route(ComedyState(phase="human_review")) == "human"

    def test_route_routing_feedback_to_process_feedback(self, supervisor):
        assert supervisor.route(ComedyState(phase="routing_feedback")) == "process_feedback"

    def test_route_searching_to_search(self, supervisor):
        assert supervisor.route(ComedyState(phase="searching")) == "search"

    def test_route_chatting_to_chat(self, supervisor):
        assert supervisor.route(ComedyState(phase="chatting")) == "chat"

    def test_route_finalizing_to_finalize(self, supervisor):
        assert supervisor.route(ComedyState(phase="finalizing")) == "finalize"

    def test_route_complete_to_end(self, supervisor):
        assert supervisor.route(ComedyState(phase="complete")) == "__end__"


def _make_creative_mock_llm(section_texts: list[str]) -> MagicMock:
    """构造写作节点用的 mock LLM（普通文本输出）。"""
    llm = MagicMock()
    llm.invoke.side_effect = [MagicMock(content=text) for text in section_texts]
    # 写作节点不使用结构化输出，但为避免误触发，返回空 mock
    llm.with_structured_output.return_value.invoke.return_value = MagicMock()
    return llm


def _make_analytical_mock_llm(
    intent: UserIntent = UserIntent.WRITING,
    analysis: AnalysisResult | None = None,
    plan: PlanResult | None = None,
    review: ReviewResult | None = None,
) -> MagicMock:
    """构造分析类节点用的 mock LLM（结构化输出）。"""
    from tests.conftest import make_structured_mock_llm

    analysis = analysis or AnalysisResult(
        topic="通勤", attitude="讽刺", bias="无", emotion="无奈"
    )
    plan = plan or PlanResult(
        todo=["分析", "写作"],
        outline=["铺垫", "展开", "callback 收尾"],
        tone="讽刺",
    )
    review = review or ReviewResult(
        decision="修改", comments="再犀利一点", score=7
    )
    return make_structured_mock_llm(
        responses={
            IntentClassification: IntentClassification(
                intent=intent, confidence=0.95, reasoning="包含创作关键词"
            ),
            AnalysisResult: analysis,
            PlanResult: plan,
            ReviewResult: review,
        }
    )


class TestSupervisorFlow:
    """Supervisor 图端到端流程测试。"""

    def test_writing_path_to_interrupt(self, graph):
        """创作路径：应停在第一段人类审阅。"""
        analytical_llm = _make_analytical_mock_llm()
        creative_llm = _make_creative_mock_llm(["第一段内容"])

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
                ComedyState(
                    user_input="写一段关于通勤的脱口秀",
                    slots={
                        "话题": "通勤",
                        "态度": "讽刺",
                        "偏见": "无",
                        "情绪": "无奈",
                    },
                ),
                config={"configurable": {"thread_id": "sm-writing"}},
            )

        assert "__interrupt__" in result
        interrupt = result["__interrupt__"][0].value
        assert interrupt["section_text"] == "第一段内容"

    def test_chat_path_to_end(self, graph):
        """闲聊路径：chat 后直接结束。"""
        from tests.conftest import make_structured_mock_llm

        analytical_llm = make_structured_mock_llm(
            responses={
                IntentClassification: IntentClassification(
                    intent=UserIntent.CHAT, confidence=0.9, reasoning="普通问候"
                ),
            }
        )
        chat_llm = MagicMock()
        chat_llm.invoke.return_value = MagicMock(content="你好！有什么可以帮你的？")
        chat_llm.with_structured_output.return_value.invoke.return_value = MagicMock()

        with patch("comedy_agent.nodes.entry_node.ModelFactory") as mock_entry, \
             patch("comedy_agent.nodes.chat_node.ModelFactory") as mock_chat:
            mock_entry.get_model.return_value = analytical_llm
            mock_chat.get_model.return_value = chat_llm

            result = graph.invoke(
                ComedyState(user_input="你好"),
                config={"configurable": {"thread_id": "sm-chat"}},
            )

        final = ComedyState.model_validate(result)
        assert final.phase == "complete"
        assert "你好" in final.output

    def test_plan_shape(self):
        """验证 plan_node 生成的 plan 包含必要字段。"""
        from comedy_agent.nodes.plan_node import plan_node
        from tests.conftest import make_structured_mock_llm

        analytical_llm = make_structured_mock_llm(
            responses={
                PlanResult: PlanResult(
                    todo=["t1"],
                    outline=["o1", "o2", "o3"],
                    tone="讽刺",
                ),
            }
        )

        with patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_factory:
            mock_factory.get_model.return_value = analytical_llm
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
        assert result["plan"]["tone"] == "讽刺"
        assert result["phase"] == "writing"
