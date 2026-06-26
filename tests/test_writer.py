"""Writer Agent 测试。"""

from unittest.mock import MagicMock

import pytest

from comedy_agent.agents.writer import WriterAgent
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def mock_llm():
    m = MagicMock()
    m.invoke.return_value = MagicMock(content="这是生成的段落。")
    return m


class TestWriterAgent:
    def test_moves_to_finalizing_when_done(self):
        state = ComedyState(
            plan={"outline": ["第一段"]},
            current_section=1,
        )
        agent = WriterAgent()
        result = agent.run(state)
        assert result["phase"] == "finalizing"

    def test_generates_section_with_default_skill(self, mock_llm):
        state = ComedyState(
            user_input="讲讲加班",
            plan={"outline": ["开头", "冲突"]},
            current_section=0,
            sections=[],
        )
        agent = WriterAgent()
        result = agent.run(state, llm=mock_llm)

        assert result["phase"] == "reviewing"
        assert result["sections"] == ["这是生成的段落。"]
        assert result["skill_meta"]["skill_id"] == "my_skill"

        # 验证调用了 LLM 且包含 system + human 两条消息
        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0][0] == "system"
        assert call_args[1][0] == "human"

    def test_generates_section_with_selected_skill(self, mock_llm):
        state = ComedyState(
            user_input="讲讲加班",
            plan={"outline": ["开头", "冲突"]},
            current_section=0,
            sections=[],
            selected_skill="zhou_qimo",
        )
        agent = WriterAgent()
        result = agent.run(state, llm=mock_llm)

        assert result["phase"] == "reviewing"
        assert result["skill_meta"]["skill_id"] == "zhou_qimo"

        # 验证 system prompt 包含了周奇墨风格的关键词
        call_args = mock_llm.invoke.call_args[0][0]
        system_prompt = call_args[0][1]
        assert "周奇墨" in system_prompt or "观察" in system_prompt

    def test_unknown_skill_fallback_to_my_skill(self, mock_llm):
        state = ComedyState(
            user_input="讲讲加班",
            plan={"outline": ["开头"]},
            current_section=0,
            selected_skill="not_exists",
        )
        agent = WriterAgent()
        result = agent.run(state, llm=mock_llm)

        assert result["phase"] == "reviewing"
        assert result["skill_meta"]["skill_id"] == "my_skill"
