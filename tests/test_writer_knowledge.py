"""测试 Writer 集成知识检索（Push 模式）。"""

import pytest
from langchain_core.messages import AIMessage

from comedy_agent.agents.writer import WriterAgent
from comedy_agent.core.knowledge_models import KnowledgeItem
from comedy_agent.state.schema import ComedyState


class FakeLLM:
    """返回固定文本的 LLM 替身。"""

    def __init__(self, content="这是生成的段落。"):
        self._content = content

    def invoke(self, messages):
        return AIMessage(content=self._content)


@pytest.fixture
def sample_state() -> ComedyState:
    return ComedyState(
        user_input="写一段关于加班的脱口秀",
        plan={"outline": ["铺垫", "冲突", "callback 收尾"]},
        current_section=0,
        sections=[],
        selected_skill="my_skill",
        selected_style="自嘲",
        user_id="test-user",
    )


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
    ]


class TestWriterKnowledge:
    """Writer 知识 Push 模式测试。"""

    def test_writer_records_knowledge_references(
        self, monkeypatch, sample_state, knowledge_items
    ):
        monkeypatch.setattr(
            "comedy_agent.agents.writer.retrieve_examples",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "comedy_agent.agents.writer.retrieve_knowledge",
            lambda query, top_k: knowledge_items,
        )

        result = WriterAgent().run(sample_state, llm=FakeLLM())
        skill_meta = result.get("skill_meta", {})
        assert "knowledge_references" in skill_meta
        refs = skill_meta["knowledge_references"]
        assert len(refs) == 1
        assert refs[0]["title"] == "三番四抖"

    def test_writer_prompt_contains_knowledge_context(
        self, monkeypatch, sample_state, knowledge_items
    ):
        captured_messages = None

        class CapturingLLM:
            def invoke(self, messages):
                nonlocal captured_messages
                captured_messages = messages
                return AIMessage(content="生成段落")

        monkeypatch.setattr(
            "comedy_agent.agents.writer.retrieve_examples",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "comedy_agent.agents.writer.retrieve_knowledge",
            lambda query, top_k: knowledge_items,
        )

        WriterAgent().run(sample_state, llm=CapturingLLM())

        assert captured_messages is not None
        prompt_text = "\n".join(
            str(m[1]) if isinstance(m, tuple) else str(m.content)
            for m in captured_messages
        )
        assert "【理论知识参考】" in prompt_text
        assert "三番四抖" in prompt_text

    def test_writer_gracefully_handles_knowledge_error(
        self, monkeypatch, sample_state
    ):
        monkeypatch.setattr(
            "comedy_agent.agents.writer.retrieve_examples",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "comedy_agent.agents.writer.retrieve_knowledge",
            lambda query, top_k: (_ for _ in ()).throw(RuntimeError("检索失败")),
        )

        result = WriterAgent().run(sample_state, llm=FakeLLM())
        skill_meta = result.get("skill_meta", {})
        assert skill_meta.get("knowledge_references", []) == []
