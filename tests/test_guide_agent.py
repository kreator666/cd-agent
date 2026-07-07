"""GuideAgent 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.agents.guide import GuideAgent
from comedy_agent.state.schema import ComedyState


def _make_llm(content: str) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=content)
    return llm


@pytest.fixture
def agent():
    return GuideAgent()


def test_guide_parses_abc_options(agent):
    """正常解析回复与 A/B/C 选项。"""
    content = (
        "回复: 我们可以先确定话题\n"
        "选项:\n"
        "A. @话题 加班\n"
        "B. @话题 通勤\n"
        "C. 什么是好的话题？"
    )
    result = agent.run(
        ComedyState(user_input="我不知道写什么", phase="consulting"),
        llm=_make_llm(content),
    )
    assert result["response_type"] == "guide"
    assert result["phase"] == "consulting"
    assert "确定话题" in result["output"]
    assert len(result["suggested_actions"]) == 3
    assert result["suggested_actions"][0]["value"] == "@话题 加班"


def test_guide_fills_missing_options(agent):
    """选项不足 3 个时，使用兜底补全。"""
    content = "回复: 请继续\n选项:\nA. 继续"
    result = agent.run(
        ComedyState(user_input="继续", phase="consulting"),
        llm=_make_llm(content),
    )
    assert len(result["suggested_actions"]) == 3


def test_guide_fallback_for_missing_slots(agent):
    """LLM 失败且槽位缺失时，返回填槽建议。"""
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("API error")
    result = agent.run(
        ComedyState(
            user_input="怎么填槽",
            phase="consulting",
            slots={"话题": "加班"},
        ),
        llm=llm,
    )
    assert result["response_type"] == "guide"
    assert any("态度" in a["value"] for a in result["suggested_actions"])


def test_guide_no_llm_uses_factory(agent):
    """未传入 LLM 时，应调用 ModelFactory。"""
    from comedy_agent.models.factory import ModelFactory

    mock_llm = _make_llm(
        "回复: 测试\n选项:\nA. 选项一\nB. 选项二\nC. 选项三"
    )

    with patch.object(ModelFactory, "get_model", return_value=mock_llm):
        result = agent.run(ComedyState(user_input="测试", phase="consulting"))

    assert result["response_type"] == "guide"
    assert len(result["suggested_actions"]) == 3


def test_guide_uses_collection_prompt_when_slots_missing(agent):
    """槽位缺失且 Skill 提供 collection_prompt.md 时，应使用教练式收集提示词。"""
    llm = _make_llm(
        "回复: 我们可以先确定话题\n选项:\nA. @话题 加班\nB. @话题 通勤\nC. 什么是好的话题？"
    )
    state = ComedyState(
        user_input="我想写脱口秀",
        phase="consulting",
        slots={"话题": "加班"},
        selected_skill="standup",
    )
    result = agent.run(state, llm=llm)

    assert result["response_type"] == "guide"
    prompt = llm.invoke.call_args[0][0][0][1]
    assert "脱口秀" in prompt or "四维度收集阶段" in prompt


def test_guide_uses_topic_skill_when_topic_missing(agent):
    """当前 Skill 无 collection_prompt 且话题缺失时，应使用 topic Skill 的引导 prompt。"""
    llm = _make_llm(
        "回复: 你想聊这个话题的哪个方面？\n选项:\nA. 加班本身\nB. 老板的奇葩要求\nC. 同事的内卷"
    )
    state = ComedyState(
        user_input="我想写加班",
        phase="consulting",
        slots={},
        selected_skill="standup",
    )
    result = agent.run(state, llm=llm)

    assert result["response_type"] == "guide"
    prompt = llm.invoke.call_args[0][0][0][1]
    assert "话题引导师" in prompt or "深挖子话题" in prompt or "话题缺失时" in prompt


def test_guide_uses_topic_skill_to_deepen_topic(agent):
    """话题已填充但用户刚聊完话题时，应继续用 topic Skill 深挖子话题。"""
    llm = _make_llm(
        "回复: 你想重点讲暴富后的哪个场景？\n选项:\nA. 被绑架的焦虑\nB. 挥霍的日常\nC. 三千万带来的社交变化"
    )
    state = ComedyState(
        user_input="@话题 假如我有三千万",
        phase="consulting",
        slots={"话题": "假如我有三千万"},
        active_slot_dimension="话题",
        selected_skill="standup",
    )
    result = agent.run(state, llm=llm)

    assert result["response_type"] == "guide"
    prompt = llm.invoke.call_args[0][0][0][1]
    assert "话题引导师" in prompt or "深挖子话题" in prompt or "话题已给出" in prompt


def test_guide_falls_back_to_default_prompt_when_slots_full(agent):
    """槽位已全时，应回退到默认引导提示词。"""
    llm = _make_llm(
        "回复: 4 个维度齐了\n选项:\nA. 生成计划\nB. 修改槽位\nC. 直接开始写作"
    )
    state = ComedyState(
        user_input="开始吧",
        phase="consulting",
        slots={"话题": "加班", "态度": "难", "偏见": "剥削", "情绪": "愤怒"},
        selected_skill="standup",
    )
    result = agent.run(state, llm=llm)

    assert result["response_type"] == "guide"
    prompt = llm.invoke.call_args[0][0][0][1]
    assert "专业的喜剧创作助手" in prompt
    assert "四维度收集阶段" not in prompt
