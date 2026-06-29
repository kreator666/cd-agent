"""ReviewerAgent 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from comedy_agent.agents.reviewer import ReviewerAgent
from comedy_agent.agents.schemas import ReviewDecision, ReviewResult
from comedy_agent.state.schema import ComedyState


def _make_llm(content: str) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=content)
    return llm


class TestReviewerTextFallback:
    """测试结构化输出失败时的文本兜底解析。"""

    def test_fallback_parses_markdown_list(self):
        """LLM 返回 markdown 列表时，应正确提取 decision/comments/score。"""
        agent = ReviewerAgent()
        content = (
            "- decision: 修改\n"
            "- comments: 节奏可以再紧凑一点\n"
            "- score: 7"
        )
        result = agent._text_fallback(_make_llm(content), "prompt")

        assert isinstance(result, ReviewResult)
        assert result.decision == ReviewDecision.MODIFY
        assert "节奏" in result.comments
        assert result.score == 7

    def test_fallback_parses_json_block(self):
        """LLM 返回 JSON 代码块时，应直接解析。"""
        agent = ReviewerAgent()
        content = '```json\n{"decision": "通过", "comments": "很好", "score": 9}\n```'
        result = agent._text_fallback(_make_llm(content), "prompt")

        assert result.decision == ReviewDecision.APPROVE
        assert "很好" in result.comments
        assert result.score == 9

    def test_fallback_unknown_decision_defaults_to_modify(self):
        """decision 无法识别时，默认按 修改 处理。"""
        agent = ReviewerAgent()
        content = "- decision: 再看看\n- comments: 一般\n- score: 5"
        result = agent._text_fallback(_make_llm(content), "prompt")

        assert result.decision == ReviewDecision.MODIFY
        assert result.score == 5


class TestReviewerAgentRun:
    def test_run_with_no_sections_returns_default_approve(self):
        """没有段落时直接返回通过，不调用 LLM。"""
        agent = ReviewerAgent()
        llm = MagicMock()
        state = ComedyState(sections=[], current_section=0)

        result = agent.run(state, llm=llm)

        assert result["phase"] == "human_review"
        assert result["review"]["decision"] == ReviewDecision.APPROVE.value
        llm.invoke.assert_not_called()
