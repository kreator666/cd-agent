"""用户认证（大V）功能测试。"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
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


def _register_and_login(client, user_id, password="Test123!"):
    client.post("/auth/register", json={"user_id": user_id, "password": password})
    r = client.post("/auth/login", json={"user_id": user_id, "password": password})
    return r.json()["access_token"]


class TestVerificationApply:
    def test_apply_verification_success(self, client):
        """普通用户可以提交认证申请。"""
        token = _register_and_login(client, "user1")
        res = client.post(
            "/me/verify-apply",
            json={"reason": "我是喜剧创作者"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "pending"
        assert data["reason"] == "我是喜剧创作者"

    def test_duplicate_pending_application(self, client):
        """已有 pending 申请时再次提交应返回已有记录。"""
        token = _register_and_login(client, "user2")
        client.post(
            "/me/verify-apply",
            json={"reason": "第一次申请"},
            headers={"Authorization": f"Bearer {token}"},
        )
        res = client.post(
            "/me/verify-apply",
            json={"reason": "第二次申请"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["reason"] == "第一次申请"  # 应返回第一次的申请

    def test_get_my_verification(self, client):
        """可以查询自己的认证状态。"""
        token = _register_and_login(client, "user3")
        client.post(
            "/me/verify-apply",
            json={"reason": "测试查询"},
            headers={"Authorization": f"Bearer {token}"},
        )
        res = client.get(
            "/me/verification",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "pending"
        assert data["reason"] == "测试查询"

    def test_get_verification_not_found(self, client):
        """没有申请记录时返回 404。"""
        token = _register_and_login(client, "user4")
        res = client.get(
            "/me/verification",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404


class TestVerificationAdminReview:
    def test_admin_approve_verification(self, client):
        """admin 通过认证申请后，用户 is_verified 变为 true。"""
        user_token = _register_and_login(client, "creator1")
        admin_token = _register_and_login(client, "admin")

        # 用户提交申请
        apply_res = client.post(
            "/me/verify-apply",
            json={"reason": "请通过我"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        app_id = apply_res.json()["id"]

        # admin 通过
        res = client.post(
            f"/admin/verifications/{app_id}/approve",
            json={},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "approved"

        # 用户资料中 is_verified 应为 true
        me_res = client.get("/me", headers={"Authorization": f"Bearer {user_token}"})
        assert me_res.json()["is_verified"] is True

    def test_admin_reject_verification(self, client):
        """admin 拒绝认证申请。"""
        user_token = _register_and_login(client, "creator2")
        admin_token = _register_and_login(client, "admin")

        apply_res = client.post(
            "/me/verify-apply",
            json={"reason": "这次会被拒绝"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        app_id = apply_res.json()["id"]

        res = client.post(
            f"/admin/verifications/{app_id}/reject",
            json={"review_note": "资料不足"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "rejected"
        assert data["review_note"] == "资料不足"

        # 用户资料中 is_verified 仍为 false
        me_res = client.get("/me", headers={"Authorization": f"Bearer {user_token}"})
        assert me_res.json()["is_verified"] is False

    def test_non_admin_cannot_review(self, client):
        """非 admin 无法调用审核接口。"""
        user_token = _register_and_login(client, "user5")
        res = client.post(
            "/admin/verifications/1/approve",
            json={},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert res.status_code == 403

    def test_public_profile_shows_is_verified(self, client):
        """公开资料中包含 is_verified 字段。"""
        user_token = _register_and_login(client, "creator3")
        admin_token = _register_and_login(client, "admin")

        apply_res = client.post(
            "/me/verify-apply",
            json={},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        app_id = apply_res.json()["id"]
        client.post(
            f"/admin/verifications/{app_id}/approve",
            json={},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        res = client.get("/users/creator3")
        assert res.status_code == 200
        assert res.json()["is_verified"] is True
