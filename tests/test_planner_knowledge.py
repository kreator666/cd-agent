"""测试 Planner 集成知识检索（Pull 模式）。"""

import pytest
from langchain_core.messages import AIMessage

from comedy_agent.agents.planner import PlannerAgent
from comedy_agent.core.knowledge_models import KnowledgeItem
from comedy_agent.state.schema import ComedyState


class FakeLLM:
    """返回固定计划文本的 LLM 替身。"""

    def __init__(self, content):
        self._content = content

    def invoke(self, messages):
        return AIMessage(content=self._content)


@pytest.fixture
def sample_plan_text():
    return """
todo:
1. 分析话题
2. 生成大纲
3. 逐段写作

outline:
1. 开场铺垫
2. 展开观察
3. 转折升级
4. callback 收尾

tone: 讽刺自嘲
"""


@pytest.fixture
def knowledge_items():
    return [
        KnowledgeItem(
            id="three-setup-four-punch",
            title="三番四抖",
            category="technique",
            content="三番四抖是相声经典结构技巧。",
            summary="通过三次铺垫和一次转折制造笑点。",
            source="comedy_theory.md",
        ),
        KnowledgeItem(
            id="callback",
            title="Callback",
            category="technique",
            content="Callback 是回扣前面笑点。",
            summary="回扣前面笑点。",
            source="喜剧通用技法",
        ),
    ]


class TestPlannerKnowledge:
    """Planner 知识 Pull 模式测试。"""

    def test_planner_includes_knowledge_references(
        self, monkeypatch, sample_plan_text, knowledge_items
    ):
        monkeypatch.setattr(
            "comedy_agent.agents.planner.retrieve_knowledge",
            lambda query, top_k: knowledge_items,
        )

        state = ComedyState(
            user_input="写一段关于加班的脱口秀",
            analysis={
                "topic": "加班",
                "attitude": "讽刺",
                "bias": "无",
                "emotion": "无奈",
            },
        )
        llm = FakeLLM(sample_plan_text)
        result = PlannerAgent().run(state, llm=llm)

        plan = result["plan"]
        assert "knowledge_references" in plan
        refs = plan["knowledge_references"]
        assert len(refs) == len(knowledge_items)
        assert refs[0]["title"] == "三番四抖"

    def test_planner_prompt_contains_knowledge_context(
        self, monkeypatch, sample_plan_text, knowledge_items
    ):
        captured_prompt = None

        class CapturingLLM:
            def invoke(self, messages):
                nonlocal captured_prompt
                # messages: [(role, content), ...]
                captured_prompt = "\n".join(
                    str(m[1]) if isinstance(m, tuple) else str(m.content)
                    for m in messages
                )
                return AIMessage(content=sample_plan_text)

        monkeypatch.setattr(
            "comedy_agent.agents.planner.retrieve_knowledge",
            lambda query, top_k: knowledge_items,
        )

        state = ComedyState(
            user_input="写一段关于加班的脱口秀",
            analysis={
                "topic": "加班",
                "attitude": "讽刺",
                "bias": "无",
                "emotion": "无奈",
            },
        )
        PlannerAgent().run(state, llm=CapturingLLM())

        assert captured_prompt is not None
        assert "三番四抖" in captured_prompt
        assert "Callback" in captured_prompt

    def test_planner_gracefully_handles_retrieval_error(self, monkeypatch, sample_plan_text):
        monkeypatch.setattr(
            "comedy_agent.agents.planner.retrieve_knowledge",
            lambda query, top_k: (_ for _ in ()).throw(RuntimeError("检索失败")),
        )

        state = ComedyState(
            user_input="写一段关于加班的脱口秀",
            analysis={
                "topic": "加班",
                "attitude": "讽刺",
                "bias": "无",
                "emotion": "无奈",
            },
        )
        llm = FakeLLM(sample_plan_text)
        result = PlannerAgent().run(state, llm=llm)

        plan = result["plan"]
        # 即使检索失败，也不应抛错，且 knowledge_references 为空或不存在
        assert plan.get("knowledge_references", []) == []
