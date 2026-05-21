"""偏好提取器单元测试。"""

import pytest

from comedy_agent.memory.preference_extractor import (
    _build_conversation_text,
    _extract_json,
)


class TestBuildConversationText:
    def test_empty_messages(self):
        assert _build_conversation_text([]) == ""

    def test_basic_messages(self):
        messages = [
            {"role": "human", "content": "写一个吐槽职场的脱口秀"},
            {"role": "ai", "content": "好的，以下是..."},
        ]
        text = _build_conversation_text(messages)
        assert "用户: 写一个吐槽职场的脱口秀" in text
        assert "AI: 好的，以下是..." in text

    def test_skips_empty_content(self):
        messages = [
            {"role": "human", "content": "hello"},
            {"role": "ai", "content": ""},
            {"role": "ai", "content": "reply"},
        ]
        text = _build_conversation_text(messages)
        assert "hello" in text
        assert "reply" in text
        assert text.count("\n\n") == 1  # 只有两条有效消息

    def test_truncates_long_content(self):
        long_text = "x" * 500
        messages = [{"role": "human", "content": long_text}]
        text = _build_conversation_text(messages)
        assert len(text) < len(long_text) + 50  # 应该被截断到300字


class TestExtractJson:
    def test_pure_json(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_json_with_markdown(self):
        assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_json_with_text(self):
        assert _extract_json('some text {"a": 1} more') == {"a": 1}

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            _extract_json("not json at all")

    def test_nested_json(self):
        data = _extract_json('{"preferences": {"style": "吐槽风"}}')
        assert data["preferences"]["style"] == "吐槽风"
