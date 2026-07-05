"""消息转换工具测试。"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from comedy_agent.utils.messages import dicts_to_messages, messages_to_dicts


class TestDictsToMessages:
    def test_human_and_ai(self):
        dicts = [
            {"role": "human", "content": "你好"},
            {"role": "ai", "content": "你好，有什么可以帮你的？"},
        ]
        messages = dicts_to_messages(dicts)
        assert len(messages) == 2
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "你好"
        assert isinstance(messages[1], AIMessage)
        assert messages[1].content == "你好，有什么可以帮你的？"

    def test_role_aliases(self):
        dicts = [
            {"role": "user", "content": "用户消息"},
            {"role": "assistant", "content": "助手消息"},
            {"role": "bot", "content": "机器人消息"},
        ]
        messages = dicts_to_messages(dicts)
        assert isinstance(messages[0], HumanMessage)
        assert isinstance(messages[1], AIMessage)
        assert isinstance(messages[2], AIMessage)

    def test_system_and_tool(self):
        dicts = [
            {"role": "system", "content": "系统提示"},
            {"role": "tool", "content": "工具结果", "tool_call_id": "call_123"},
        ]
        messages = dicts_to_messages(dicts)
        assert isinstance(messages[0], SystemMessage)
        assert isinstance(messages[1], ToolMessage)
        assert messages[1].tool_call_id == "call_123"

    def test_unknown_role_fallback(self):
        messages = dicts_to_messages([{"role": "unknown", "content": "未知消息"}])
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "未知消息"

    def test_skip_non_dict_items(self):
        messages = dicts_to_messages([{"role": "human", "content": "ok"}, None, "invalid"])
        assert len(messages) == 1


class TestMessagesToDicts:
    def test_roundtrip(self):
        original = [
            HumanMessage(content="你好"),
            AIMessage(content="你好"),
            SystemMessage(content="系统提示"),
        ]
        dicts = messages_to_dicts(original)
        restored = dicts_to_messages(dicts)
        assert len(restored) == 3
        assert all(a.content == b.content for a, b in zip(original, restored))

    def test_tool_message(self):
        messages = [ToolMessage(content="结果", tool_call_id="call_abc")]
        dicts = messages_to_dicts(messages)
        assert dicts[0]["role"] == "tool"
        assert dicts[0]["tool_call_id"] == "call_abc"
