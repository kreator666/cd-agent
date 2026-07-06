"""ContextAnalyzerAgent 测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from comedy_agent.agents.context_analyzer import ContextAnalyzerAgent
from comedy_agent.agents.schemas import AnalysisResult
from comedy_agent.state.schema import ComedyState


def test_analyzer_prompt_includes_conversation_history():
    """分析 Prompt 应包含完整对话历史和已有槽位。"""
    agent = ContextAnalyzerAgent()
    llm = MagicMock()
    captured = {}

    def _capture(messages):
        # messages 格式 [("human", prompt)]
        captured["prompt"] = messages[0][1] if isinstance(messages[0], tuple) else messages[0].content
        return AnalysisResult(topic="加班", attitude="讽刺", bias="无", emotion="无奈")

    structured = MagicMock()
    structured.invoke.side_effect = _capture
    llm.with_structured_output.return_value = structured

    agent.run(
        ComedyState(
            user_input="开始创作",
            slots={"话题": "加班", "态度": "讽刺"},
            messages=[
                HumanMessage(content="我想写加班"),
                AIMessage(content="好的，请补充态度"),
                HumanMessage(content="态度讽刺"),
            ],
        ),
        llm=llm,
    )

    prompt = captured["prompt"]
    assert "用户：我想写加班" in prompt
    assert "用户：态度讽刺" in prompt
    assert "助手：好的，请补充态度" in prompt
    assert "话题" in prompt
    assert "态度" in prompt


def test_analyzer_prompt_includes_slot_conversations():
    """分析 Prompt 应包含各维度专项对话历史。"""
    agent = ContextAnalyzerAgent()
    llm = MagicMock()
    captured = {}

    def _capture(messages):
        captured["prompt"] = messages[0][1] if isinstance(messages[0], tuple) else messages[0].content
        return AnalysisResult(topic="通勤", attitude="讽刺", bias="无", emotion="无奈")

    structured = MagicMock()
    structured.invoke.side_effect = _capture
    llm.with_structured_output.return_value = structured

    agent.run(
        ComedyState(
            user_input="开始创作",
            slots={"话题": "通勤", "态度": "讽刺", "偏见": "无", "情绪": "无奈"},
            slot_conversations={
                "话题": [
                    HumanMessage(content="@话题 加班"),
                    AIMessage(content="收到，话题是加班。"),
                    HumanMessage(content="@话题 其实是通勤"),
                ]
            },
        ),
        llm=llm,
    )

    prompt = captured["prompt"]
    assert "【话题】" in prompt
    assert "@话题 加班" in prompt
    assert "其实是通勤" in prompt
    assert "收到，话题是加班" in prompt


def test_analyzer_fallback_uses_previous_analysis():
    """结构化失败时，文本兜底也应基于完整历史。"""
    agent = ContextAnalyzerAgent()
    llm = MagicMock()
    captured = {}

    # 让结构化输出抛异常
    structured = MagicMock()
    structured.invoke.side_effect = ValueError("mock error")
    llm.with_structured_output.return_value = structured

    def _capture(messages):
        captured["prompt"] = messages[0][1] if isinstance(messages[0], tuple) else messages[0].content
        return MagicMock(content='{"topic": "相亲", "attitude": "自嘲", "bias": "无", "emotion": "尴尬"}')

    llm.invoke.side_effect = _capture

    result = agent.run(
        ComedyState(
            user_input="开始创作",
            analysis={"topic": "相亲", "attitude": "自嘲", "bias": "无", "emotion": "尴尬"},
            messages=[HumanMessage(content="相亲"), HumanMessage(content="很尴尬")],
        ),
        llm=llm,
    )

    assert captured["prompt"]
    assert result["analysis"]["topic"] == "相亲"
