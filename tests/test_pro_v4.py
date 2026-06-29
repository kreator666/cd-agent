"""专业版 B /pro/chat-v4 接口测试。"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langgraph.types import Command
from sqlalchemy import StaticPool, create_engine

from comedy_agent.api.server import app, state


def _patched_create_engine(*args, **kwargs):
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


@pytest.fixture
def client():
    """提供已认证的 TestClient，graph 被 mock。"""
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
        mock_orch.list_skills.return_value = [
            {"name": "standup_generator", "description": "", "task_type": "creative", "source": "builtin"}
        ]
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore

        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store

        with TestClient(app) as c:
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")

            c.post("/auth/register", json={"user_id": "prouser", "password": "testpass"})
            login = c.post("/auth/login", json={"user_id": "prouser", "password": "testpass"})
            token = login.json()["access_token"]

            with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as authed_c:
                state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
                yield authed_c

    state.orch = None
    state.graph = None
    state.memory = None


class TestProV4State:
    def test_non_feedback_request_uses_command_update(self, client):
        """非反馈请求应使用 Command(update=...) 而不是完整 ComedyState，避免覆盖历史状态。"""
        from comedy_agent.api.server import state

        state.graph.get_state.return_value = MagicMock(values={"phase": "idle"})
        state.graph.ainvoke = AsyncMock(
            return_value={
                "phase": "consulting",
                "output": "请补充态度",
                "slots": {"话题": "加班"},
            }
        )
        state.graph.update_state.return_value = None

        resp = client.post(
            "/pro/chat-v4",
            json={"message": "我想写一段关于加班的脱口秀"},
        )
        assert resp.status_code == 200

        call_args = state.graph.ainvoke.call_args
        invoked = call_args.args[0]
        assert isinstance(invoked, Command)
        assert "user_input" in invoked.update
        assert invoked.update["user_input"] == "我想写一段关于加班的脱口秀"
        # 不能带 slots / analysis / plan，否则会用默认值覆盖 checkpoint
        assert "slots" not in invoked.update
        assert "analysis" not in invoked.update
        assert "plan" not in invoked.update

    def test_feedback_request_uses_command_resume(self, client):
        """反馈请求应使用 Command(resume=...)。"""
        from comedy_agent.api.server import state

        state.graph.get_state.return_value = MagicMock(values={"phase": "plan_review"})
        state.graph.ainvoke = AsyncMock(return_value={"phase": "complete", "output": "好的"})

        resp = client.post(
            "/pro/chat-v4",
            json={"message": "通过"},
        )
        assert resp.status_code == 200

        invoked = state.graph.ainvoke.call_args.args[0]
        assert isinstance(invoked, Command)
        assert invoked.resume == "通过"
