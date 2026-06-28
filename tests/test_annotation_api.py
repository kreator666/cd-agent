"""标注与反馈接口测试。"""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from comedy_agent.api.server import app, state


def _patched_create_engine(*args, **kwargs):
    """对 SQLite 内存数据库使用 StaticPool。"""
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


@pytest.fixture
def client():
    """提供已认证的 TestClient，memory 使用内存数据库，向量库被 mock。"""
    with patch("comedy_agent.api.server.VectorStore"), patch(
        "comedy_agent.api.server.ComedyRetriever"
    ), patch("comedy_agent.api.server.build_chat_graph"), patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ), patch(
        "comedy_agent.api.server.AgentOrchestrator"
    ) as mock_orch_cls, patch(
        "comedy_agent.auth.router.SQLMemoryStore"
    ) as mock_auth_store_cls, patch(
        "comedy_agent.api.routers.annotations.ingest_annotations"
    ) as mock_ingest:
        mock_orch = MagicMock()
        mock_orch.list_skills.return_value = [
            {"name": "standup_generator", "description": "", "task_type": "creative", "source": "builtin"}
        ]
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore

        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store
        mock_ingest.side_effect = lambda annotations, **kw: [f"fake-id-{i}" for i in range(len(annotations))]

        with TestClient(app) as c:
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")

            c.post("/auth/register", json={"user_id": "annuser", "password": "testpass"})
            login = c.post("/auth/login", json={"user_id": "annuser", "password": "testpass"})
            token = login.json()["access_token"]

            with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as authed_c:
                state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
                yield authed_c

    state.orch = None
    state.graph = None
    state.memory = None


class TestAnnotationCreate:
    def test_create_annotation_success(self, client):
        payload = {
            "content": "我特别喜欢上班，那种每天起早贪黑的感觉特别让我着迷。",
            "setup": "我特别喜欢上班",
            "punchline": "那种每天起早贪黑的感觉特别让我着迷",
            "tags": ["职场", "反讽"],
            "topic": "上班",
            "style": "反讽",
            "kind": "standup",
            "structure_type": "one_liner",
            "humor_score": 7,
        }
        resp = client.post("/annotations", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["example_id"]
        assert data["collection"] == "user_knowledge_annuser"

    def test_create_annotation_missing_content(self, client):
        resp = client.post("/annotations", json={"content": ""})
        assert resp.status_code == 422


class TestAnnotationIngest:
    def test_ingest_annotations_batch(self, client):
        payload = {
            "examples": [
                {
                    "content": "示例一",
                    "topic": "测试",
                    "kind": "standup",
                    "embedding_text": "话题：测试\n文本：示例一",
                },
                {
                    "content": "示例二",
                    "topic": "测试",
                    "kind": "standup",
                    "embedding_text": "话题：测试\n文本：示例二",
                },
            ]
        }
        resp = client.post("/annotations/ingest", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ingested_count"] == 2
        assert len(data["ids"]) == 2
        assert data["collection"] == "user_knowledge_annuser"


class TestFeedbackMessage:
    def test_feedback_message_up(self, client):
        resp = client.post(
            "/annotations/feedback/message",
            json={
                "target_type": "message",
                "target_id": "msg-1",
                "rating": 1,
                "comment": "很好",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"]

    def test_feedback_message_down(self, client):
        resp = client.post(
            "/annotations/feedback/message",
            json={
                "target_type": "artifact",
                "target_id": "art-1",
                "rating": -1,
            },
        )
        assert resp.status_code == 200

    def test_feedback_invalid_rating(self, client):
        resp = client.post(
            "/annotations/feedback/message",
            json={
                "target_type": "message",
                "target_id": "msg-2",
                "rating": 2,
            },
        )
        assert resp.status_code == 422

    def test_list_feedback_events(self, client):
        client.post(
            "/annotations/feedback/message",
            json={
                "target_type": "message",
                "target_id": "msg-3",
                "rating": 1,
            },
        )
        resp = client.get("/annotations/feedback/events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) >= 1
        assert data["events"][0]["target_id"] == "msg-3"
