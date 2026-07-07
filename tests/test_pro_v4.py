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
                "phase": "consulting",
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
            json={"message": "态度是讽刺"},
        )
        assert resp.status_code == 200

        invoked = state.graph.ainvoke.call_args.args[0]
        assert isinstance(invoked, ComedyState)
        # 必须重置为 idle，否则上一轮 complete 会直接结束
        assert invoked.phase == "idle"
        assert invoked.user_input == "态度是讽刺"
        # 历史状态必须被保留，而不是被默认值覆盖
        assert invoked.slots == {"话题": "加班"}
        assert invoked.analysis == {"topic": "加班", "attitude": "讽刺"}
        assert invoked.plan == {"todo": ["t1"], "outline": ["o1"], "tone": "讽刺"}
        # 本轮用户消息应被追加
        assert len(invoked.messages) == 1
        assert isinstance(invoked.messages[0], HumanMessage)
        assert invoked.messages[0].content == "态度是讽刺"
        # GuideAgent 需要的能力列表应被注入
        assert invoked.available_skills == ["standup_generator"]

    def test_duration_parameter_passed_to_state(self, client):
        """请求中的 duration 应被写入 ComedyState。"""
        from comedy_agent.api.server import state

        state.graph.get_state.return_value = MagicMock(
            values={
                "phase": "consulting",
                "slots": {"话题": "三千万"},
                "analysis": {"topic": "三千万"},
                "plan": {"todo": ["t1"], "outline": ["o1"], "tone": "荒诞"},
                "messages": [],
            }
        )
        state.graph.ainvoke = AsyncMock(
            return_value={"phase": "complete", "output": "生成完成"}
        )
        state.graph.update_state.return_value = None

        resp = client.post(
            "/pro/chat-v4",
            json={"message": "开始写作", "duration": 5},
        )
        assert resp.status_code == 200

        invoked = state.graph.ainvoke.call_args.args[0]
        assert isinstance(invoked, ComedyState)
        assert invoked.duration == 5

    def test_new_creation_request_clears_previous_analysis_and_plan(self, client):
        """新创作请求开始时，应清理上一轮已完成的 analysis / plan，避免旧计划被复用。"""
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
                "output": "好的，重新聊",
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
        assert invoked.phase == "idle"
        # 新一轮创作请求应清空旧分析/计划
        assert invoked.analysis is None
        assert invoked.plan is None

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

    def test_memory_fallback_when_checkpoint_empty(self, client):
        """checkpoint 为空时，应从 memory 加载历史并回填到 messages。"""
        from comedy_agent.api.server import state

        state.graph.get_state.return_value = None
        state.graph.ainvoke = AsyncMock(
            return_value={
                "phase": "complete",
                "output": "继续的回复",
            }
        )
        state.graph.update_state.return_value = None

        mock_conv = MagicMock()
        mock_conv.messages = [
            {"role": "human", "content": "上一句"},
            {"role": "ai", "content": "上一答"},
        ]
        mock_conv.summary = "测试摘要"
        state.memory.load_conversation = MagicMock(return_value=mock_conv)

        resp = client.post(
            "/pro/chat-v4",
            json={"message": "继续", "session_id": "fallback-session"},
        )
        assert resp.status_code == 200

        invoked = state.graph.ainvoke.call_args.args[0]
        assert isinstance(invoked, ComedyState)
        # messages 应包含从 memory 回填的历史 + 当前输入
        assert len(invoked.messages) == 3
        assert invoked.messages[0].content == "上一句"
        assert invoked.messages[1].content == "上一答"
        assert invoked.messages[2].content == "继续"
        # 摘要也应被回填
        assert invoked.conversation_summary == "测试摘要"
        # 验证调用了 memory 加载
        state.memory.load_conversation.assert_called_once_with("prouser", "fallback-session")

    def test_memory_fallback_loads_slot_conversations(self, client):
        """checkpoint 为空时，应从 memory 加载维度独立对话历史。"""
        from comedy_agent.api.server import state

        state.graph.get_state.return_value = None
        state.graph.ainvoke = AsyncMock(
            return_value={
                "phase": "complete",
                "output": "继续的回复",
            }
        )
        state.graph.update_state.return_value = None

        mock_conv = MagicMock()
        mock_conv.messages = []
        mock_conv.summary = None
        mock_conv.slot_conversations = {
            "话题": [{"role": "human", "content": "@话题 加班"}],
            "态度": [{"role": "human", "content": "@态度 讽刺"}],
        }
        state.memory.load_conversation = MagicMock(return_value=mock_conv)

        resp = client.post(
            "/pro/chat-v4",
            json={"message": "继续", "session_id": "slot-session"},
        )
        assert resp.status_code == 200

        invoked = state.graph.ainvoke.call_args.args[0]
        assert isinstance(invoked, ComedyState)
        assert invoked.slot_conversations is not None
        assert invoked.slot_conversations["话题"][0].content == "@话题 加班"
        assert invoked.slot_conversations["态度"][0].content == "@态度 讽刺"

    def test_ai_reply_archived_to_active_slot_dimension(self, client):
        """AI 回复应归档到当前活跃维度的独立对话历史中。"""
        from comedy_agent.api.server import state

        state.graph.get_state.return_value = MagicMock(
            values={
                "phase": "consulting",
                "active_slot_dimension": "话题",
                "slot_conversations": {
                    "话题": [HumanMessage(content="@话题 加班")]
                },
            }
        )
        state.graph.ainvoke = AsyncMock(
            return_value={
                "phase": "consulting",
                "output": "收到，话题是加班",
            }
        )
        state.graph.update_state.return_value = None

        resp = client.post(
            "/pro/chat-v4",
            json={"message": "@话题 加班"},
        )
        assert resp.status_code == 200

        # 验证 update_state 被调用以追加 AI 消息到 slot_conversations
        update_calls = [call.args for call in state.graph.update_state.call_args_list]
        slot_conv_update = [c for c in update_calls if len(c) > 1 and "slot_conversations" in c[1]]
        assert len(slot_conv_update) == 1
        updated = slot_conv_update[0][1]["slot_conversations"]
        assert "话题" in updated
        assert updated["话题"][0].content == "收到，话题是加班"

    def test_save_conversation_persists_slot_conversations(self, client):
        """保存会话时应持久化维度独立对话历史。"""
        from comedy_agent.api.server import state

        state.graph.get_state.return_value = MagicMock(
            values={
                "phase": "complete",
                "messages": [HumanMessage(content="@话题 加班")],
                "slot_conversations": {
                    "话题": [HumanMessage(content="@话题 加班")]
                },
            }
        )
        state.graph.ainvoke = AsyncMock(
            return_value={
                "phase": "complete",
                "output": "收到",
            }
        )
        state.graph.update_state.return_value = None
        state.memory.save_conversation = MagicMock()

        resp = client.post(
            "/pro/chat-v4",
            json={"message": "@话题 加班", "session_id": "persist-session"},
        )
        assert resp.status_code == 200

        save_call = state.memory.save_conversation.call_args
        assert save_call is not None
        saved_slot_conversations = save_call.kwargs.get("slot_conversations")
        assert saved_slot_conversations is not None
        assert saved_slot_conversations["话题"][0]["content"] == "@话题 加班"

    def test_chat_v4_conversation_can_be_deleted(self, client):
        """/pro/chat-v4 创建的会话应能通过 DELETE /conversations/{session_id} 删除。"""
        from comedy_agent.api.server import state

        state.graph.get_state.return_value = MagicMock(
            values={
                "phase": "complete",
                "messages": [HumanMessage(content="写一段脱口秀")],
                "slot_conversations": {},
            }
        )
        state.graph.ainvoke = AsyncMock(
            return_value={
                "phase": "complete",
                "output": "好的，请告诉我话题",
            }
        )
        state.graph.update_state.return_value = None

        # 使用真实 memory 保存会话
        from comedy_agent.memory.unified import UnifiedMemory

        state.memory = UnifiedMemory(db_url="sqlite:///:memory:")

        resp = client.post(
            "/pro/chat-v4",
            json={"message": "写一段脱口秀", "session_id": "delete-me-session"},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # 验证会话已保存
        get_resp = client.get(f"/conversations/{session_id}")
        assert get_resp.status_code == 200

        # 删除会话
        del_resp = client.delete(f"/conversations/{session_id}")
        assert del_resp.status_code == 200

        # 验证已删除
        get_resp2 = client.get(f"/conversations/{session_id}")
        assert get_resp2.status_code == 404
