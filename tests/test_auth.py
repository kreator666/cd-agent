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
        mock_orch_cls.return_value = mock_orch

        # auth router 使用内存数据库
        from comedy_agent.memory.medium_term import SQLMemoryStore
        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store

        with TestClient(app) as c:
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
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
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "meuser"
        assert data["nickname"] == "Me"
