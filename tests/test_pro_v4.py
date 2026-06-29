"""专业版 B /pro/chat-v4 接口测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage
from langgraph.types import Command
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
    def test_non_feedback_request_uses_merged_comedystate(self, client):
        """非反馈请求应读取 checkpoint、合并历史状态，并用 ComedyState 重新跑图。"""
        from comedy_agent.api.server import state

        state.graph.get_state.return_value = MagicMock(
            values={
                "phase": "complete",
                "slots": {"话题": "加班"},
                "analysis": {"topic": "加班", "attitude": "讽刺"},
                "plan": {"todo": ["t1"], "outline": ["o1"], "tone": "讽刺"},
                "messages": [],
            }
        )
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

        invoked = state.graph.ainvoke.call_args.args[0]
        assert isinstance(invoked, ComedyState)
        # 必须重置为 idle，否则上一轮 complete 会直接结束
        assert invoked.phase == "idle"
        assert invoked.user_input == "我想写一段关于加班的脱口秀"
        # 历史状态必须被保留，而不是被默认值覆盖
        assert invoked.slots == {"话题": "加班"}
        assert invoked.analysis == {"topic": "加班", "attitude": "讽刺"}
        assert invoked.plan == {"todo": ["t1"], "outline": ["o1"], "tone": "讽刺"}
        # 本轮用户消息应被追加
        assert len(invoked.messages) == 1
        assert isinstance(invoked.messages[0], HumanMessage)
        assert invoked.messages[0].content == "我想写一段关于加班的脱口秀"

    def test_non_feedback_request_response_changes_with_input(self, client):
        """不同输入应产生不同回复，验证图确实被重新执行。"""
        from comedy_agent.api.server import state

        state.graph.get_state.return_value = MagicMock(values={"phase": "complete"})

        async def _dynamic_invoke(invoked, config=None):
            user_input = invoked.user_input if isinstance(invoked, ComedyState) else ""
            return {
                "phase": "complete",
                "output": f"针对「{user_input}」的回复",
            }

        state.graph.ainvoke = AsyncMock(side_effect=_dynamic_invoke)
        state.graph.update_state.return_value = None

        resp1 = client.post("/pro/chat-v4", json={"message": "输入 A"})
        resp2 = client.post("/pro/chat-v4", json={"message": "输入 B"})

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert "输入 A" in resp1.json()["content"]
        assert "输入 B" in resp2.json()["content"]
        assert resp1.json()["content"] != resp2.json()["content"]

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
