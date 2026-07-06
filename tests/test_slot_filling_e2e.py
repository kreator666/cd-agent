"""@ 填槽端到端流程测试。

验证用户通过 @维度 填充槽位后，状态正确保持为 consulting，
槽位被持久化，且可以逐步填充剩余槽位。
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


def _make_guide_llm(content: str) -> MagicMock:
    """构造 GuideAgent 用的 mock LLM。"""
    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content=content)
    return llm


@patch("comedy_agent.agents.guide.ModelFactory.get_model")
@patch("comedy_agent.agents.intent_classifier.ModelFactory.get_model")
@patch("comedy_agent.nodes.entry_node.ModelFactory.get_model")
def test_at_emotion_fills_slot_and_stays_consulting(
    mock_entry_factory,
    mock_intent_factory,
    mock_guide_factory,
    chat_graph,
):
    """@情绪 提交后应填充情绪槽位，并保持在 consulting 等待后续输入。"""
    guide_llm = _make_guide_llm(
        "回复: 收到，情绪已记录，继续补充其他维度\n"
        "选项:\n"
        "A. @话题 加班\n"
        "B. @态度 自嘲\n"
        "C. @偏见 老板"
    )
    mock_guide_factory.return_value = guide_llm
    mock_intent_factory.return_value = MagicMock()
    mock_entry_factory.return_value = MagicMock()

    thread_id = "test-slot-emotion"
    raw_result = chat_graph.invoke(
        ComedyState(
            phase="idle",
            user_input="@情绪 开心",
            messages=[HumanMessage(content="@情绪 开心")],
            session_id=thread_id,
            user_id="test",
        ),
        config={"configurable": {"thread_id": thread_id}},
    )
    result = ComedyState.model_validate(raw_result)

    assert result.slots is not None
    assert result.slots.get("情绪") == "开心"
    assert result.phase == "consulting"
    assert result.response_type == "guide"
    assert result.output is not None

    # checkpoint 中也应保留槽位
    checkpoint = chat_graph.get_state({"configurable": {"thread_id": thread_id}})
    assert checkpoint.values["slots"]["情绪"] == "开心"
    assert checkpoint.values["phase"] == "consulting"
