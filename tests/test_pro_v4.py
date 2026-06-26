"""专业版 B (/pro/chat-v4) 接口测试。"""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from comedy_agent.api.server import app, state
from comedy_agent.state.schema import ComedyState


def _patched_create_engine(*args, **kwargs):
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


@pytest.fixture
def client():
    """提供带认证的 TestClient，v4 Graph 为 mock。"""
    with patch("comedy_agent.api.server.VectorStore"), patch(
        "comedy_agent.api.server.ComedyRetriever"
    ), patch("comedy_agent.api.server.build_chat_graph"), patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ), patch(
        "comedy_agent.api.server.AgentOrchestrator"
    ) as mock_orch_cls, patch(
        "comedy_agent.auth.router.SQLMemoryStore"
    ) as mock_auth_store_cls:
        mock_orch = MagicMock()
        mock_orch.list_skills.return_value = []
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore

        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store

        with TestClient(app) as c:
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
            c.post("/auth/register", json={"user_id": "testuser", "password": "testpass"})
            login_resp = c.post(
                "/auth/login", json={"user_id": "testuser", "password": "testpass"}
            )
            token = login_resp.json()["access_token"]

            with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as authed_c:
                state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
                yield authed_c

    state.orch = None
    state.graph = None
    state.memory = None


class TestProChatV4:
    """/pro/chat-v4 接口测试。"""

    def test_chat_v4_complete(self, client):
        """v4 Graph 正常完成时，返回 final_script 类型响应。"""
        from comedy_agent.api.server import state

        async def _ainvoke(state_input, config=None):
            return ComedyState(
                output="最终剧本内容",
                phase="complete",
                response_type="script",
                analysis={"topic": "通勤", "attitude": "讽刺"},
                slots={"话题": "通勤", "态度": "讽刺", "偏见": "无", "情绪": "无奈"},
            )

        state.graph = MagicMock()
        state.graph.get_state.return_value = None
        state.graph.ainvoke = _ainvoke

        response = client.post(
            "/pro/chat-v4",
            json={"message": "写一段关于通勤的脱口秀"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "final_script"
        assert data["content"] == "最终剧本内容"
        assert data["workflow_state"] == "complete"
        assert any(a["type"] == "script" for a in (data.get("artifacts") or []))
        assert data["slots"].get("话题") == "通勤"

    def test_chat_v4_slot_guide(self, client):
        """槽位未填满时，返回 guide 引导用户继续填槽。"""
        from comedy_agent.api.server import state

        async def _ainvoke(state_input, config=None):
            return ComedyState(
                output="请先填满 4 个维度",
                phase="complete",
                response_type="guide",
                slots={"话题": "通勤"},
            )

        state.graph = MagicMock()
        state.graph.get_state.return_value = None
        state.graph.ainvoke = _ainvoke

        response = client.post(
            "/pro/chat-v4",
            json={"message": "写一段关于通勤的脱口秀"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "guide"
        assert "话题" in data["slots"]

    def test_chat_v4_interrupt(self, client):
        """v4 Graph 触发 interrupt 时，返回 human_review 引导。"""
        from comedy_agent.api.server import state

        class _InterruptValue:
            value = {"message": "请审阅", "section_text": "第一段内容"}

        async def _ainvoke(state_input, config=None):
            return {"__interrupt__": [_InterruptValue()]}

        state.graph = MagicMock()
        state.graph.get_state.return_value = None
        state.graph.ainvoke = _ainvoke

        response = client.post(
            "/pro/chat-v4",
            json={"message": "写一段关于通勤的脱口秀"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "guide"
        assert data["workflow_state"] == "human_review"
        assert "第一段内容" in data["content"]
        assert data["current_role"] == "reviewer"

    def test_chat_v4_resume_feedback(self, client):
        """处于 human_review 时，用户消息作为 feedback 恢复。"""
        from comedy_agent.api.server import state

        async def _ainvoke(state_input, config=None):
            return ComedyState(
                output="最终剧本",
                phase="complete",
                response_type="script",
            )

        state.graph = MagicMock()
        snapshot = MagicMock()
        snapshot.values = {"phase": "human_review"}
        state.graph.get_state.return_value = snapshot
        state.graph.ainvoke = _ainvoke

        response = client.post(
            "/pro/chat-v4",
            json={"message": "通过", "session_id": "sess-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "final_script"
        assert data["content"] == "最终剧本"

    def test_chat_v4_load_session(self, client):
        """加载会话状态。"""
        from comedy_agent.api.server import state

        state.graph = MagicMock()
        snapshot = MagicMock()
        snapshot.values = ComedyState(
            output="已完成的剧本",
            phase="complete",
            response_type="script",
        ).model_dump()
        state.graph.get_state.return_value = snapshot

        response = client.get("/pro/chat-v4/sess-load")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "final_script"
        assert data["content"] == "已完成的剧本"
