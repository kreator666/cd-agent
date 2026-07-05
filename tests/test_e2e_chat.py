"""v4 LangGraph Chat 端到端测试。

直接测试 graph.builder.build_chat_graph()，通过 mock LLM 避免依赖真实 API Key。
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from comedy_agent.graph.builder import build_chat_graph
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def chat_graph():
    """提供编译后的 Chat Graph，使用临时 SQLite checkpoint 数据库。"""
    fd, tmp_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    with patch("comedy_agent.checkpoints.memory.settings.memory_db_path", tmp_path):
        from comedy_agent.checkpoints.memory import CheckpointSaverFactory

        CheckpointSaverFactory._instance = None
        graph = build_chat_graph()
        yield graph
        # 关闭数据库连接，确保临时文件可被删除
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
        os.unlink(tmp_path)
    except (FileNotFoundError, PermissionError):
        pass


def test_chat_graph_compiles():
    """图可以正常编译。"""
    graph = build_chat_graph()
    assert graph is not None
    assert "chat" in graph.nodes


def test_chat_graph_state_validation():
    """非法状态应触发 Pydantic ValidationError。"""
    with pytest.raises(ValueError):
        ComedyState(phase="invalid_phase")


def test_chat_graph_basic_flow(chat_graph):
    """最基本 Chat 端到端流程。"""
    mock_response = AIMessage(content="这是一个测试回复")

    with patch("comedy_agent.nodes.chat_node.ModelFactory") as mock_factory:
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=mock_response)
        mock_factory.get_model.return_value = mock_llm

        raw_result = chat_graph.invoke(
            ComedyState(user_input="你好"),
            config={"configurable": {"thread_id": "test-thread-1"}},
        )
        result = ComedyState.model_validate(raw_result)

    assert result.output == "这是一个测试回复"
    assert result.phase == "complete"
    assert len(result.messages) == 3  # system + human + ai
    assert isinstance(result.messages[1], HumanMessage)
    assert isinstance(result.messages[2], AIMessage)

    # 验证 LLM 被调用时包含 system + human 消息
    call_args = mock_llm.invoke.call_args[0][0]
    assert len(call_args) == 2
    assert call_args[0].type == "system"
    assert call_args[1].type == "human"
    assert call_args[1].content == "你好"


def test_chat_graph_with_history(chat_graph):
    """带历史消息的 Chat 流程。"""
    mock_response = AIMessage(content="继续的回复")

    with patch("comedy_agent.nodes.chat_node.ModelFactory") as mock_factory:
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=mock_response)
        mock_factory.get_model.return_value = mock_llm

        raw_result = chat_graph.invoke(
            ComedyState(
                user_input="继续",
                chat_history=[("human", "上一句"), ("ai", "上一答")],
            ),
            config={"configurable": {"thread_id": "test-thread-2"}},
        )
        result = ComedyState.model_validate(raw_result)

    assert result.output == "继续的回复"
    call_args = mock_llm.invoke.call_args[0][0]
    assert len(call_args) == 4  # system + 2 history + current human
    assert call_args[1].content == "上一句"
    assert call_args[2].content == "上一答"
    assert call_args[3].content == "继续"


def test_chat_graph_checkpoint_recovery(chat_graph):
    """checkpoint 能保存并恢复状态。

    同一 thread_id 多次调用应能正常执行，且最终状态可读取。
    消息累积行为将在 Phase 1+ 配合 add_messages reducer 完整验证。
    """
    mock_response = AIMessage(content="checkpoint 测试")

    with patch("comedy_agent.nodes.chat_node.ModelFactory") as mock_factory:
        mock_llm = MagicMock()
        mock_llm.invoke = MagicMock(return_value=mock_response)
        mock_factory.get_model.return_value = mock_llm

        thread_id = "test-thread-3"
        chat_graph.invoke(
            ComedyState(user_input="第一次"),
            config={"configurable": {"thread_id": thread_id}},
        )

        # 同一 thread_id 再次调用，不应报错，且能拿到结果
        raw_result = chat_graph.invoke(
            ComedyState(user_input="第二次"),
            config={"configurable": {"thread_id": thread_id}},
        )
        result = ComedyState.model_validate(raw_result)

    assert result.output == "checkpoint 测试"
