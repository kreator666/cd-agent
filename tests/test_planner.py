"""PlannerAgent 测试。"""

from __future__ import annotations

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
