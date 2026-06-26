"""IntentClassifierAgent 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.agents.intent_classifier import IntentClassifierAgent
from comedy_agent.agents.schemas import IntentClassification, UserIntent
from comedy_agent.state.schema import ComedyState
from tests.conftest import make_structured_mock_llm


@pytest.fixture
def agent():
    return IntentClassifierAgent()


@pytest.mark.parametrize(
    "user_input,expected_intent",
    [
        ("写一段关于加班的脱口秀", UserIntent.WRITING),
        ("来个小品", UserIntent.WRITING),
        ("搜索一下最近的 comedy 理论", UserIntent.SEARCH),
        ("停止创作", UserIntent.CONTROL),
        ("你好", UserIntent.CHAT),
    ],
)
def test_intent_classification_structured(agent, user_input, expected_intent):
    """LLM 结构化输出正常时，分类结果正确。"""
    llm = make_structured_mock_llm(
        responses={
            IntentClassification: IntentClassification(
                intent=expected_intent, confidence=0.9, reasoning="mock"
            ),
        }
    )

    result = agent.run(
        ComedyState(user_input=user_input, phase="idle"),
        llm=llm,
    )

    assert result["intent"] == expected_intent.value
    assert result["phase"] == agent._intent_to_phase(expected_intent.value, "idle")


def test_intent_classification_fallback_on_structured_error(agent):
    """结构化输出失败时，使用规则兜底。"""
    llm = MagicMock()
    llm.with_structured_output.side_effect = RuntimeError("API error")

    result = agent.run(
        ComedyState(user_input="写一段关于婚姻的脱口秀", phase="idle"),
        llm=llm,
    )

    assert result["intent"] == "writing"
    assert result["phase"] == "analyzing"


def test_intent_classifier_no_llm_uses_factory(agent):
    """未传入 LLM 时，应调用 ModelFactory。"""
    from comedy_agent.models.factory import ModelFactory

    mock_llm = make_structured_mock_llm(
        responses={
            IntentClassification: IntentClassification(
                intent=UserIntent.CHAT, confidence=0.9
            ),
        }
    )

    with patch.object(ModelFactory, "get_model", return_value=mock_llm):
        result = agent.run(ComedyState(user_input="你好", phase="idle"))

    assert result["intent"] == "chat"
