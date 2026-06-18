"""用户认证模块单元测试。"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from comedy_agent.api.server import app, state


def _patched_create_engine(*args, **kwargs):
    """对 SQLite 内存数据库使用 StaticPool，确保多线程共享连接。"""
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


@pytest.fixture
def client():
    """提供 TestClient（使用内存数据库）。"""
    with patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ), patch("comedy_agent.api.server.AgentOrchestrator") as mock_orch_cls, patch(
        "comedy_agent.auth.router.SQLMemoryStore"
    ) as mock_auth_store_cls:
        mock_orch = MagicMock()
        mock_orch.list_skills.return_value = ["standup_generator"]
        mock_orch.run.return_value = {"output": "test response", "messages": []}
        mock_orch_cls.return_value = mock_orch

        # auth router 使用内存数据库
        from comedy_agent.memory.medium_term import SQLMemoryStore
        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store

        with TestClient(app) as c:
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
            state.memory._store = auth_store
            yield c

    state.orch = None
    state.memory = None


class TestRegister:
    def test_register_success(self, client):
        response = client.post(
            "/auth/register",
            json={"user_id": "testuser", "password": "secret123", "nickname": "Test"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "testuser"
        assert data["nickname"] == "Test"

    def test_register_duplicate(self, client):
        # 第一次注册
        r1 = client.post(
            "/auth/register",
            json={"user_id": "dupuser", "password": "secret123"},
        )
        assert r1.status_code == 200

        # 重复注册
        r2 = client.post(
            "/auth/register",
            json={"user_id": "dupuser", "password": "secret123"},
        )
        assert r2.status_code == 409
        assert "已存在" in r2.json()["detail"]


class TestLogin:
    def test_login_success(self, client):
        # 先注册
        client.post(
            "/auth/register",
            json={"user_id": "loginuser", "password": "mypassword"},
        )

        # 登录
        response = client.post(
            "/auth/login",
            json={"user_id": "loginuser", "password": "mypassword"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user_id"] == "loginuser"

    def test_login_wrong_password(self, client):
        # 先注册
        client.post(
            "/auth/register",
            json={"user_id": "wrongpass", "password": "correct"},
        )

        # 密码错误
        response = client.post(
            "/auth/login",
            json={"user_id": "wrongpass", "password": "incorrect"},
        )
        assert response.status_code == 401
        assert "密码错误" in response.json()["detail"]

    def test_login_user_not_found(self, client):
        response = client.post(
            "/auth/login",
            json={"user_id": "notexist", "password": "whatever"},
        )
        assert response.status_code == 401


class TestProtectedRoutes:
    def test_chat_without_token(self, client):
        response = client.post("/chat", json={"prompt": "hello"})
        assert response.status_code == 401

    def test_chat_with_token(self, client):
        # 注册并登录
        client.post(
            "/auth/register",
            json={"user_id": "tokenuser", "password": "secret"},
        )
        login_resp = client.post(
            "/auth/login",
            json={"user_id": "tokenuser", "password": "secret"},
        )
        token = login_resp.json()["access_token"]

        # 访问受保护接口
        response = client.post(
            "/chat",
            json={"prompt": "hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # 由于 AgentOrchestrator 是 mock，会返回 mock 值或报错
        # 只要不是 401 就说明认证通过了
        assert response.status_code != 401

    def test_me_endpoint(self, client):
        # 注册并登录
        client.post(
            "/auth/register",
            json={"user_id": "meuser", "password": "secret", "nickname": "Me"},
        )
        login_resp = client.post(
            "/auth/login",
            json={"user_id": "meuser", "password": "secret"},
        )
        token = login_resp.json()["access_token"]

        response = client.get(
            "/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "meuser"
        assert data["nickname"] == "Me"


class TestConversations:
    def _get_token(self, client, user_id="convuser"):
        client.post("/auth/register", json={"user_id": user_id, "password": "secret"})
        login_resp = client.post("/auth/login", json={"user_id": user_id, "password": "secret"})
        return login_resp.json()["access_token"]

    def test_chat_saves_conversation(self, client):
        token = self._get_token(client)
        response = client.post(
            "/chat",
            json={"prompt": "hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] is not None
        assert len(data["session_id"]) > 0

    def test_list_conversations(self, client):
        token = self._get_token(client)
        # 先发起两次对话
        r1 = client.post("/chat", json={"prompt": "first"}, headers={"Authorization": f"Bearer {token}"})
        r2 = client.post("/chat", json={"prompt": "second"}, headers={"Authorization": f"Bearer {token}"})
        assert r1.status_code == 200
        assert r2.status_code == 200

        # 获取会话列表
        response = client.get("/conversations", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["conversations"]) == 2

    def test_get_conversation_detail(self, client):
        token = self._get_token(client)
        chat_resp = client.post("/chat", json={"prompt": "detail test"}, headers={"Authorization": f"Bearer {token}"})
        session_id = chat_resp.json()["session_id"]

        response = client.get(
            f"/conversations/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert "messages" in data

    def test_delete_conversation(self, client):
        token = self._get_token(client)
        chat_resp = client.post("/chat", json={"prompt": "delete me"}, headers={"Authorization": f"Bearer {token}"})
        session_id = chat_resp.json()["session_id"]

        # 删除
        del_resp = client.delete(
            f"/conversations/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_resp.status_code == 200

        # 确认已删除
        get_resp = client.get(
            f"/conversations/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 404

    def test_list_conversations_empty(self, client):
        token = self._get_token(client, user_id="emptyuser")
        response = client.get("/conversations", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["conversations"] == []


class TestPreferences:
    def _get_token(self, client, user_id="prefuser"):
        client.post("/auth/register", json={"user_id": user_id, "password": "secret"})
        login_resp = client.post("/auth/login", json={"user_id": user_id, "password": "secret"})
        return login_resp.json()["access_token"]

    def test_list_preferences_empty(self, client):
        token = self._get_token(client)
        response = client.get("/preferences", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["preferences"] == []

    def test_list_preferences_with_data(self, client):
        token = self._get_token(client)
        # 通过 state.memory 写入偏好（与 API 使用同一个实例）
        from comedy_agent.api.server import state
        state.memory.save_preference("prefuser", "preferred_style", "吐槽风")
        state.memory.save_preference("prefuser", "preferred_duration", "3分钟")

        response = client.get("/preferences", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        prefs = {p["key"]: p["value"] for p in data["preferences"]}
        assert prefs.get("preferred_style") == "吐槽风"
        assert prefs.get("preferred_duration") == "3分钟"
