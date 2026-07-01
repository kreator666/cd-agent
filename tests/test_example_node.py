"""样例引导写作节点测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from comedy_agent.nodes.example_node import (
    example_generator_node,
    example_review_node,
    _parse_examples,
)
from comedy_agent.state.schema import ComedyState


class TestParseExamples:
    """测试样例解析。"""

    def test_parse_json_object(self):
        text = '{"examples": ["a", "b", "c"]}'
        assert _parse_examples(text) == ["a", "b", "c"]

    def test_parse_json_array(self):
        text = '["x", "y"]'
        assert _parse_examples(text) == ["x", "y"]

    def test_parse_markdown_code_block(self):
        text = '```json\n{"examples": ["样例1", "样例2"]}\n```'
        assert _parse_examples(text) == ["样例1", "样例2"]

    def test_parse_fallback_lines(self):
        text = "- 第一行\n- 第二行\n- 第三行"
        assert _parse_examples(text) == ["第一行", "第二行", "第三行"]

    def test_parse_empty_fallback(self):
        assert _parse_examples("") == ["（未能生成样例，请直接输入本段内容）"]


class TestExampleGeneratorNode:
    """测试样例生成节点。"""

    def test_generates_three_examples(self):
        state = ComedyState(
            plan={"outline": ["段落目标"]},
            current_section=0,
            analysis={"topic": "加班", "attitude": "吐槽", "bias": "老板", "emotion": "愤怒"},
            selected_skill="standup_coach",
        )
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='{"examples": ["a", "b", "c"]}')

        result = example_generator_node(state, llm=mock_llm)

        assert result["phase"] == "example_review"
        assert result["section_examples"] == ["a", "b", "c"]
        mock_llm.invoke.assert_called_once()

    def test_fallback_on_invalid_output(self):
        state = ComedyState(
            plan={"outline": ["段落目标"]},
            current_section=0,
            analysis={},
        )
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="不是 JSON")

        result = example_generator_node(state, llm=mock_llm)

        assert result["phase"] == "example_review"
        assert len(result["section_examples"]) == 3

    def test_pads_to_three_examples(self):
        state = ComedyState(
            plan={"outline": ["段落目标"]},
            current_section=0,
            analysis={},
        )
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='{"examples": ["only"]}')

        result = example_generator_node(state, llm=mock_llm)

        assert len(result["section_examples"]) == 3
        assert result["section_examples"][0] == "only"


class TestExampleReviewNode:
    """测试样例审阅/收集节点。"""

    def test_writes_user_draft_to_sections(self):
        state = ComedyState(
            plan={"outline": ["第一段", "第二段"]},
            current_section=0,
            section_examples=["a", "b", "c"],
            sections=[],
        )

        def fake_interrupt(payload):
            assert "section_examples" in payload
            return "用户写的段落"

        import comedy_agent.nodes.example_node as example_node
        original_interrupt = example_node.interrupt
        example_node.interrupt = fake_interrupt
        try:
            result = example_review_node(state)
        finally:
            example_node.interrupt = original_interrupt

        assert result["phase"] == "reviewing"
        assert result["sections"] == ["用户写的段落"]
        assert result["user_draft"] == "用户写的段落"
        assert result["section_examples"] is None

    def test_overwrites_existing_section(self):
        state = ComedyState(
            plan={"outline": ["第一段"]},
            current_section=0,
            section_examples=["a", "b", "c"],
            sections=["旧段落"],
        )

        def fake_interrupt(payload):
            return "新段落"

        import comedy_agent.nodes.example_node as example_node
        original_interrupt = example_node.interrupt
        example_node.interrupt = fake_interrupt
        try:
            result = example_review_node(state)
        finally:
            example_node.interrupt = original_interrupt

        assert result["sections"] == ["新段落"]
