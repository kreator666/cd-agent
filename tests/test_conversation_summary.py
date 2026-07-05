"""长对话摘要功能测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from comedy_agent.agents.context_analyzer import _format_history
from comedy_agent.utils.summarizer import summarize_messages


class TestSummarizeMessages:
    @pytest.mark.asyncio
    async def test_empty_messages_returns_empty(self):
        assert await summarize_messages([]) == ""

    @pytest.mark.asyncio
    async def test_summarize_messages_calls_llm(self):
        messages = [
            HumanMessage(content="我想写一段关于加班的脱口秀"),
            AIMessage(content="好的，请告诉我你的态度是什么？"),
            HumanMessage(content="态度是讽刺"),
        ]

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="摘要不重要"))

        with patch("comedy_agent.utils.summarizer.ModelFactory.get_model", return_value=mock_llm):
            result = await summarize_messages(messages)

        assert result == "摘要不重要"
        mock_llm.ainvoke.assert_called_once()
        call_messages = mock_llm.ainvoke.call_args[0][0]
        assert len(call_messages) == 1
        assert "加班" in call_messages[0].content

    @pytest.mark.asyncio
    async def test_summarize_messages_failure_returns_empty(self):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM 失败"))

        with patch("comedy_agent.utils.summarizer.ModelFactory.get_model", return_value=mock_llm):
            result = await summarize_messages([HumanMessage(content="hi")])

        assert result == ""


class TestFormatHistoryWithSummary:
    def test_without_summary(self):
        messages = [HumanMessage(content="你好"), AIMessage(content="你好")]
        text = _format_history(messages)
        assert "历史摘要" not in text
        assert "用户：你好" in text

    def test_with_summary(self):
        messages = [HumanMessage(content="你好"), AIMessage(content="你好")]
        text = _format_history(messages, summary="用户想写脱口秀")
        assert "历史摘要" in text
        assert "用户想写脱口秀" in text
        assert "最近对话" in text
