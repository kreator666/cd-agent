"""IntentClassifierAgent 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.agents.intent_classifier import IntentClassifierAgent
from comedy_agent.agents.schemas import UserIntent
from comedy_agent.state.schema import ComedyState


def _make_plain_llm(content: str) -> MagicMock:
    """构造返回固定文本的 mock LLM。"""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=content)
    return llm


@pytest.fixture
def agent():
    return IntentClassifierAgent()


@pytest.mark.parametrize(
    "user_input,llm_content,expected_intent,expected_phase",
    [
        (
            "写一段关于加班的脱口秀",
            "意图: writing\n置信度: 0.9\n理由: 用户要求创作",
            UserIntent.WRITING,
            "filling_slots",
        ),
        (
            "来个小品",
            "意图: writing\n置信度: 0.9\n理由: 用户要求创作",
            UserIntent.WRITING,
            "filling_slots",
        ),
        (
            "@话题 加班",
            "意图: fill_slot\n置信度: 0.9\n理由: 用户填写槽位",
            UserIntent.FILL_SLOT,
            "filling_slots",
        ),
        (
            "态度：讽刺",
            "意图: fill_slot\n置信度: 0.9\n理由: 用户填写槽位",
            UserIntent.FILL_SLOT,
            "filling_slots",
        ),
        (
            "搜索一下最近的 comedy 理论",
            "意图: search\n置信度: 0.9\n理由: 用户想搜索",
            UserIntent.SEARCH,
            "searching",
        ),
        (
            "停止创作",
            "意图: control\n置信度: 0.9\n理由: 用户要停止",
            UserIntent.CONTROL,
            "finalizing",
        ),
        (
            "你好",
            "意图: chat\n置信度: 0.9\n理由: 普通问候",
            UserIntent.CHAT,
            "chatting",
        ),
        (
            "我不知道该怎么填槽",
            "意图: consult\n置信度: 0.8\n理由: 用户不确定",
            UserIntent.CONSULT,
            "consulting",
        ),
    ],
)
def test_intent_classification(agent, user_input, llm_content, expected_intent, expected_phase):
    """LLM 文本输出正常时，分类结果正确。"""
    result = agent.run(
        ComedyState(user_input=user_input, phase="idle"),
        llm=_make_plain_llm(llm_content),
    )
    assert result["intent"] == expected_intent.value
    assert result["phase"] == expected_phase


def test_intent_classification_parses_keywords_when_no_label(agent):
    """输出不含标准格式时，根据关键词解析意图。"""
    result = agent.run(
        ComedyState(user_input="写一段关于婚姻的脱口秀", phase="idle"),
        llm=_make_plain_llm("这是一个创作请求"),
    )
    assert result["intent"] == "writing"
    assert result["phase"] == "filling_slots"


def test_intent_classification_rule_fallback_on_llm_error(agent):
    """LLM 调用失败时，使用规则兜底。"""
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("API error")

    result = agent.run(
        ComedyState(user_input="写一段关于婚姻的脱口秀", phase="idle"),
        llm=llm,
    )

    assert result["intent"] == "writing"
    assert result["phase"] == "filling_slots"


def test_intent_classifier_no_llm_uses_factory(agent):
    """未传入 LLM 时，应调用 ModelFactory。"""
    from comedy_agent.models.factory import ModelFactory

    mock_llm = _make_plain_llm("意图: chat\n置信度: 0.9\n理由: 普通问候")

    with patch.object(ModelFactory, "get_model", return_value=mock_llm):
        result = agent.run(ComedyState(user_input="你好", phase="idle"))

    assert result["intent"] == "chat"


def test_intent_classification_for_outline_confirmation(agent):
    """用户确认「生成大纲」时应被识别为 writing，进入 filling_slots → slot_checker → analyzing。"""
    result = agent.run(
        ComedyState(user_input="确认满意，生成大纲", phase="consulting"),
        llm=_make_plain_llm("意图: writing\n置信度: 0.9\n理由: 用户确认生成大纲"),
    )
    assert result["intent"] == "writing"
    assert result["phase"] == "filling_slots"


def test_intent_classification_rule_fallback_for_outline(agent):
    """LLM 输出不规范时，「生成大纲」关键词兜底为 writing。"""
    result = agent.run(
        ComedyState(user_input="直接开始写作", phase="consulting"),
        llm=_make_plain_llm("这是开始创作的请求"),
    )
    assert result["intent"] == "writing"
    assert result["phase"] == "filling_slots"
