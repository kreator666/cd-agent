"""知识系统端到端回归测试。

验证：输入话题 → Planner Pull 知识 → Writer Push 知识 → API 响应透传引用。
"""

import pytest
from langchain_core.messages import AIMessage

from comedy_agent.agents.planner import PlannerAgent
from comedy_agent.agents.writer import WriterAgent
from comedy_agent.api.routers.pro_v4 import _build_response
from comedy_agent.core.knowledge_models import KnowledgeItem
from comedy_agent.state.schema import ComedyState


class FakeLLM:
    """按固定内容响应的 LLM 替身。"""

    def __init__(self, content):
        self._content = content

    def invoke(self, messages):
        return AIMessage(content=self._content)


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
            related_terms=["铺垫", "包袱", "笑点"],
        ),
    ]


@pytest.fixture
def planner_output_text():
    return """
todo:
1. 分析话题
2. 用三番四抖结构生成大纲
3. 逐段写作

outline:
1. 第一番：铺垫加班日常
2. 第二番：加深加班痛苦
3. 第三番：加班到最高点
4. 第四抖：反转，原来在梦里

tone: 讽刺自嘲
"""


class TestKnowledgeE2E:
    """知识系统全链路测试。"""

    def test_planner_pulls_knowledge_and_references_it(
        self, monkeypatch, knowledge_items, planner_output_text
    ):
        monkeypatch.setattr(
            "comedy_agent.agents.planner.retrieve_knowledge",
            lambda query, top_k: knowledge_items,
        )

        state = ComedyState(
            user_input="用三番四抖的结构写一段关于加班的脱口秀",
            analysis={
                "topic": "加班",
                "attitude": "讽刺",
                "bias": "无",
                "emotion": "无奈",
            },
        )
        result = PlannerAgent().run(state, llm=FakeLLM(planner_output_text))

        plan = result["plan"]
        assert "knowledge_references" in plan
        assert any(ref["title"] == "三番四抖" for ref in plan["knowledge_references"])

    def test_writer_pushes_knowledge_and_records_references(
        self, monkeypatch, knowledge_items
    ):
        monkeypatch.setattr(
            "comedy_agent.agents.writer.retrieve_examples",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "comedy_agent.agents.writer.retrieve_knowledge",
            lambda query, top_k: knowledge_items,
        )

        state = ComedyState(
            user_input="用三番四抖的结构写一段关于加班的脱口秀",
            plan={
                "outline": ["铺垫加班", "加深痛苦", "推到最高", "反转结尾"],
                "knowledge_references": [
                    {"id": "three-setup-four-punch", "title": "三番四抖"}
                ],
            },
            current_section=0,
            sections=[],
            selected_skill="my_skill",
        )
        result = WriterAgent().run(state, llm=FakeLLM("这一段讲的是加班铺垫。"))

        skill_meta = result["skill_meta"]
        refs = skill_meta.get("knowledge_references", [])
        assert len(refs) >= 1
        assert refs[0]["title"] == "三番四抖"

    def test_api_response_transmits_knowledge_references(
        self, monkeypatch, knowledge_items
    ):
        monkeypatch.setattr(
            "comedy_agent.agents.writer.retrieve_examples",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "comedy_agent.agents.writer.retrieve_knowledge",
            lambda query, top_k: knowledge_items,
        )

        state = ComedyState(
            user_input="用三番四抖的结构写一段关于加班的脱口秀",
            plan={"outline": ["铺垫", "升级", "反转"]},
            current_section=0,
            sections=[],
            selected_skill="my_skill",
        )
        writer_result = WriterAgent().run(state, llm=FakeLLM("生成段落"))

        # 模拟最终剧本状态
        final_state = ComedyState(
            phase="complete",
            output="最终剧本",
            response_type="script",
            skill_meta=writer_result["skill_meta"],
        )
        response = _build_response(final_state, session_id="e2e-test")

        assert response.skill_meta is not None
        refs = response.skill_meta.get("knowledge_references", [])
        assert any(ref["title"] == "三番四抖" for ref in refs)
