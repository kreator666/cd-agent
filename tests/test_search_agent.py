"""SearchAgent 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.agents.search import SearchAgent
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def agent():
    return SearchAgent()


def test_search_agent_returns_results_and_output(agent):
    """SearchAgent 执行搜索后应写入 search_results 并生成 output。"""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="通勤 地铁 拥挤 段子素材")
    llm.with_structured_output.return_value.invoke.return_value = MagicMock()

    mock_tool = MagicMock()
    mock_tool.run.return_value = (
        "1. 地铁早高峰拥挤问题引发热议\n"
        "2. 打工人通勤时间平均 45 分钟\n"
        "3. 网友吐槽地铁上的奇葩行为"
    )

    with patch.object(agent, "_search_tool", mock_tool):
        result = agent.run(
            ComedyState(
                user_input="搜索一些通勤相关的脱口秀素材",
                analysis={"topic": "通勤"},
            ),
            llm=llm,
        )

    assert result["phase"] == "complete"
    assert result["search_results"]
    assert len(result["search_results"]) == 3
    assert "通勤" in result["output"]


def test_search_agent_offline_fallback(agent):
    """搜索工具不可用时返回空结果与友好提示。"""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="通勤 素材")

    with patch.object(agent, "_search_tool", None):
        result = agent.run(
            ComedyState(user_input="搜索素材", analysis={"topic": "通勤"}),
            llm=llm,
        )

    assert result["phase"] == "complete"
    assert result["search_results"] == []
    assert "没有找到相关搜索结果" in result["output"]
