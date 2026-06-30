"""draft_node 测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.nodes.draft_node import draft_node
from comedy_agent.state.schema import ComedyState


@patch("comedy_agent.nodes.draft_node.interrupt")
def test_draft_node_collects_user_draft(mock_interrupt):
    mock_interrupt.return_value = "用户根据提示写的草稿段落。"

    state = ComedyState(
        user_input="",
        plan={"outline": ["开头", "冲突", "结尾"]},
        current_section=1,
        sections=["第一段已完成"],
        coaching_hints="请从具体场景切入。",
    )

    result = draft_node(state)

    assert result["phase"] == "reviewing"
    assert result["sections"] == ["第一段已完成", "用户根据提示写的草稿段落。"]
    assert result["feedback"] == ""
    mock_interrupt.assert_called_once()
    payload = mock_interrupt.call_args[0][0]
    assert payload["coaching_hints"] == "请从具体场景切入。"
    assert payload["section_goal"] == "冲突"


@patch("comedy_agent.nodes.draft_node.interrupt")
def test_draft_node_overwrites_existing_section(mock_interrupt):
    mock_interrupt.return_value = "修改后的草稿。"

    state = ComedyState(
        user_input="",
        plan={"outline": ["开头", "冲突"]},
        current_section=0,
        sections=["旧草稿"],
        coaching_hints="重写这一段。",
    )

    result = draft_node(state)

    assert result["sections"] == ["修改后的草稿。"]
