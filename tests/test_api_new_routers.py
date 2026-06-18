"""测试新增 API Router（钱包、项目、加点盐、IP 风格、管理后台等）。"""

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
    """提供 TestClient，memory 使用内存数据库，带认证。"""
    with patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ), patch(
        "comedy_agent.api.server.AgentOrchestrator"
    ) as mock_orch_cls, patch(
        "comedy_agent.auth.router.SQLMemoryStore"
    ) as mock_auth_store_cls, patch(
        "comedy_agent.api.middleware.RateLimitMiddleware.dispatch",
        new=lambda self, request, call_next: call_next(request),
    ):
        mock_orch = MagicMock()
        mock_orch.run.return_value = {"output": "润色结果", "messages": []}
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore

        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store

        with TestClient(app) as c:
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")

            c.post("/auth/register", json={"user_id": "testuser", "password": "testpass"})
            login_resp = c.post("/auth/login", json={"user_id": "testuser", "password": "testpass"})
            token = login_resp.json()["access_token"]

            with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as authed_c:
                state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
                yield authed_c

    state.orch = None
    state.memory = None


class TestWallet:
    """钱包接口测试。"""

    def test_get_wallet(self, client):
        resp = client.get("/me/wallet")
        assert resp.status_code == 200
        data = resp.json()
        assert data["balance"] == 5000

    def test_recharge(self, client):
        resp = client.post("/me/recharge", json={"amount": 1000})
        assert resp.status_code == 200
        data = resp.json()
        assert data["balance"] == 6000
        assert data["total_recharged"] == 1000


class TestProjects:
    """项目接口测试。"""

    def test_create_and_list(self, client):
        resp = client.post("/projects", json={"name": "我的专场", "project_type": "standup"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "我的专场"
        pid = data["project_id"]

        resp = client.get("/projects")
        assert resp.status_code == 200
        assert len(resp.json()["projects"]) == 1

        resp = client.get(f"/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "我的专场"

    def test_update_and_delete(self, client):
        resp = client.post("/projects", json={"name": "旧名称"})
        pid = resp.json()["project_id"]

        resp = client.put(f"/projects/{pid}", json={"name": "新名称"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "新名称"

        resp = client.delete(f"/projects/{pid}")
        assert resp.status_code == 200

        resp = client.get(f"/projects/{pid}")
        assert resp.status_code == 404


class TestSalt:
    """加点盐接口测试。"""

    def test_salt_success(self, client):
        resp = client.post("/salt", json={"text": "今天天气不错", "salt_level": "light"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["original"] == "今天天气不错"
        assert data["token_cost"] == 10

        # 验证通过 skill 指令调用 add_salt
        from comedy_agent.api.server import state as server_state
        assert server_state.orch is not None
        call_args = server_state.orch.run.call_args
        prompt_arg = call_args[0][0] if call_args[0] else call_args[1].get("user_input", "")
        assert "add_salt" in prompt_arg

        # 验证保存为 conversation，source="salt"
        conv_resp = client.get("/conversations?limit=10")
        assert conv_resp.status_code == 200
        convs = conv_resp.json()["conversations"]
        salt_convs = [c for c in convs if c.get("source") == "salt"]
        assert len(salt_convs) == 1
        assert salt_convs[0]["metadata"]["original_text"] == "今天天气不错"
        assert salt_convs[0]["metadata"]["salt_level"] == "light"

        # 验证扣费
        wallet = client.get("/me/wallet").json()
        assert wallet["balance"] == 5000 - 10

    def test_salt_insufficient_balance(self, client):
        # 直接通过底层 store 把余额清空（testuser 是 fixture 中注册的用户）
        state.memory.deduct_tokens("testuser", 5000)
        resp = client.post("/salt", json={"text": "test", "salt_level": "medium"})
        assert resp.status_code == 402


class TestIPStyles:
    """IP 风格接口测试。"""

    def test_list_and_get(self, client):
        from comedy_agent.memory.models import IPStyleData

        state.memory.save_ip_style(
            IPStyleData(actor_name="呼兰", version="v1", description="d", prompt_snippet="p")
        )
        resp = client.get("/ip-styles")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        style_id = resp.json()[0]["style_id"]
        resp = client.get(f"/ip-styles/{style_id}")
        assert resp.status_code == 200
        assert resp.json()["actor_name"] == "呼兰"

    def test_get_not_found(self, client):
        resp = client.get("/ip-styles/not-exist")
        assert resp.status_code == 404


class TestAdmin:
    """管理后台接口测试。"""

    def test_admin_forbidden(self, client):
        resp = client.get("/admin/overview")
        assert resp.status_code == 403

    def test_banned_words(self, client):
        # 把 testuser 加入管理员白名单
        with patch("comedy_agent.api.routers.admin.ADMIN_USERS", {"testuser"}):
            resp = client.post("/admin/banned-words", json={"word": "竞品A", "category": "competitor"})
            assert resp.status_code == 200
            assert resp.json()["word"] == "竞品A"

            resp = client.get("/admin/banned-words")
            assert resp.status_code == 200
            assert len(resp.json()) == 1

            word_id = resp.json()[0]["word_id"]
            resp = client.delete(f"/admin/banned-words/{word_id}")
            assert resp.status_code == 200
