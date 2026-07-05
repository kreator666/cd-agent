"""Checkpoint 持久化测试。

验证 SqliteSaver 能跨实例恢复同一 session_id 的图状态。
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from comedy_agent.graph.builder import build_chat_graph
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def tmp_db_path():
    """提供临时 SQLite 数据库文件路径。"""
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    yield path
    # 关闭 HybridSqliteSaver 持有的连接，否则 Windows 无法删除临时文件
    from comedy_agent.checkpoints.memory import CheckpointSaverFactory

    if CheckpointSaverFactory._instance is not None:
        try:
            CheckpointSaverFactory._instance._sync_conn.close()
        except Exception:
            pass
        try:
            if CheckpointSaverFactory._instance._async_saver is not None:
                CheckpointSaverFactory._instance._async_saver.conn.close()
        except Exception:
            pass
    try:
        os.unlink(path)
    except (FileNotFoundError, PermissionError):
        pass


def test_sqlite_checkpoint_persists_history(tmp_db_path):
    """同一 session_id 在 SqliteSaver 新实例中仍能恢复历史消息。"""
    from comedy_agent.checkpoints.memory import CheckpointSaverFactory

    session_id = "persist-test-1"
    config = {"configurable": {"thread_id": session_id}}

    # 第一次：使用 SqliteSaver 运行 graph
    with patch("comedy_agent.checkpoints.memory.settings.memory_db_path", tmp_db_path):
        CheckpointSaverFactory._instance = None
        graph1 = build_chat_graph()

        mock_response = AIMessage(content="第一次回复")
        with patch("comedy_agent.nodes.chat_node.ModelFactory") as mock_factory:
            mock_llm = MagicMock()
            mock_llm.invoke = MagicMock(return_value=mock_response)
            mock_factory.get_model.return_value = mock_llm

            result1 = graph1.invoke(
                ComedyState(user_input="你好"),
                config=config,
            )

        assert result1["output"] == "第一次回复"
        # 此时 checkpoint 应已保存 system + human + ai
        saved1 = graph1.get_state(config)
        assert saved1 is not None
        assert len(saved1.values["messages"]) == 3

    # 第二次：新建 factory 实例和 graph，验证能恢复历史
    with patch("comedy_agent.checkpoints.memory.settings.memory_db_path", tmp_db_path):
        CheckpointSaverFactory._instance = None
        graph2 = build_chat_graph()

        saved2 = graph2.get_state(config)
        assert saved2 is not None
        assert len(saved2.values["messages"]) == 3
        assert isinstance(saved2.values["messages"][0], SystemMessage)
        assert isinstance(saved2.values["messages"][1], HumanMessage)
        assert isinstance(saved2.values["messages"][2], AIMessage)

        mock_response2 = AIMessage(content="第二次回复")
        with patch("comedy_agent.nodes.chat_node.ModelFactory") as mock_factory:
            mock_llm = MagicMock()
            mock_llm.invoke = MagicMock(return_value=mock_response2)
            mock_factory.get_model.return_value = mock_llm

            result2 = graph2.invoke(
                ComedyState(user_input="继续"),
                config=config,
            )

        assert result2["output"] == "第二次回复"
        # 历史应累积：system + human1 + ai1 + human2 + ai2
        final_state = graph2.get_state(config)
        assert len(final_state.values["messages"]) == 5
