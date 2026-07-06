"""PlannerAgent 测试。"""

from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from comedy_agent.agents.planner import PlannerAgent
from comedy_agent.agents.schemas import PlanResult
from comedy_agent.state.schema import ComedyState


def test_planner_prompt_includes_history_and_previous_plan():
    """Planner Prompt 应包含对话历史和上一轮计划。"""
    agent = PlannerAgent()
    llm = MagicMock()
    captured = {}

    def _capture(messages):
        captured["prompt"] = messages[0][1] if isinstance(messages[0], tuple) else messages[0].content
        return MagicMock(
            content="todo:\n1. t1\n\noutline:\n1. o1\n2. o2\n\ntone: 讽刺"
        )

    llm.invoke.side_effect = _capture

    with patch("comedy_agent.agents.planner.retrieve_knowledge", return_value=[]):
        agent.run(
            ComedyState(
                user_input="开始创作",
                analysis={"topic": "通勤", "attitude": "讽刺", "bias": "无", "emotion": "无奈"},
                plan={
                    "todo": ["旧任务"],
                    "outline": ["旧大纲1", "旧大纲2"],
                    "tone": "自嘲",
                },
                messages=[
                    HumanMessage(content="写通勤"),
                    HumanMessage(content="态度讽刺"),
                ],
            ),
            llm=llm,
        )

    prompt = captured["prompt"]
    assert "用户：写通勤" in prompt
    assert "用户：态度讽刺" in prompt
    assert "旧大纲1" in prompt
    assert "旧任务" in prompt


def test_planner_summarizes_slot_conversations_when_slots_full():
    """四个维度都填满时，Planner 应对各维度专项对话做总结。"""
    agent = PlannerAgent()
    llm = MagicMock()
    captured = {}
    summary_count = {"n": 0}

    def _capture(messages):
        captured["prompt"] = messages[0][1] if isinstance(messages[0], tuple) else messages[0].content
        return MagicMock(
            content="todo:\n1. t1\n\noutline:\n1. o1\n2. o2\n\ntone: 讽刺"
        )

    def _capture_summary(messages):
        summary_count["n"] += 1
        return MagicMock(content=f"总结{summary_count['n']}")

    def _invoke(messages):
        text = messages[0][1] if isinstance(messages[0], tuple) else messages[0].content
        if "请根据用户与助手关于" in text:
            return _capture_summary(messages)
        return _capture(messages)

    llm.invoke.side_effect = _invoke

    with patch("comedy_agent.agents.planner.retrieve_knowledge", return_value=[]):
        agent.run(
            ComedyState(
                user_input="开始创作",
                slots={"话题": "通勤", "态度": "讽刺", "偏见": "无", "情绪": "无奈"},
                analysis={"topic": "通勤", "attitude": "讽刺", "bias": "无", "emotion": "无奈"},
                slot_conversations={
                    "话题": [HumanMessage(content="@话题 通勤")],
                    "态度": [HumanMessage(content="@态度 讽刺")],
                    "偏见": [HumanMessage(content="@偏见 无")],
                    "情绪": [HumanMessage(content="@情绪 无奈")],
                },
            ),
            llm=llm,
        )

    assert summary_count["n"] == 4
    prompt = captured["prompt"]
    assert "各维度最终理解" in prompt
    assert "总结" in prompt


def test_planner_skips_summary_when_slots_incomplete():
    """四个维度未填满时，Planner 不做专项总结。"""
    agent = PlannerAgent()
    llm = MagicMock()
    captured = {}

    def _capture(messages):
        captured["prompt"] = messages[0][1] if isinstance(messages[0], tuple) else messages[0].content
        return MagicMock(
            content="todo:\n1. t1\n\noutline:\n1. o1\n2. o2\n\ntone: 讽刺"
        )

    llm.invoke.side_effect = _capture

    with patch("comedy_agent.agents.planner.retrieve_knowledge", return_value=[]):
        agent.run(
            ComedyState(
                user_input="开始创作",
                analysis={"topic": "通勤", "attitude": "讽刺", "bias": "无", "emotion": "无奈"},
                slots={"话题": "通勤"},  # 缺少态度/偏见/情绪
            ),
            llm=llm,
        )

    prompt = captured["prompt"]
    assert "维度未集齐" in prompt
