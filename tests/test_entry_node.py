"""入口节点（entry_node）单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.nodes.entry_node import entry_node
from comedy_agent.state.schema import ComedyState


@pytest.mark.parametrize(
    "user_input",
    [
        "@话题 加班",
        "@态度：讽刺",
        "@偏见 无",
        "@情绪 无奈",
    ],
)
def test_at_mention_directly_routes_to_slot_filling(user_input):
    """带 @ 的明确槽位输入直接判定为 fill_slot，不调用 LLM。"""
    with patch("comedy_agent.nodes.entry_node.ModelFactory") as mock_factory:
        result = entry_node(ComedyState(user_input=user_input))

    assert result["intent"] == "fill_slot"
    assert result["phase"] == "filling_slots"
    mock_factory.get_model.assert_not_called()


def test_non_at_input_uses_llm_for_classification():
    """不带 @ 的输入走 LLM 意图分类。"""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content="意图: writing\n置信度: 0.9\n理由: 用户要求创作"
    )

    with patch("comedy_agent.nodes.entry_node.ModelFactory") as mock_factory:
        mock_factory.get_model.return_value = mock_llm
        result = entry_node(ComedyState(user_input="写一段关于加班的脱口秀"))

    assert result["intent"] == "writing"
    assert result["phase"] == "filling_slots"
    mock_factory.get_model.assert_called_once()
