"""极速版 API 测试。"""

from __future__ import annotations

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
        "comedy_agent.memory.medium_term.create_engine", side_effect=_patched_create_engine
    ), patch("comedy_agent.api.server.AgentOrchestrator") as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch.run.return_value = {"output": "这防晒霜防水效果好得就跟我的发际线一样坚挺！", "messages": []}
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore
        store = SQLMemoryStore(db_url="sqlite:///:memory:")
        state.memory = store
        state.orch = mock_orch

        # 创建用户和 Token
        store.save_user_profile("test_user", "测试用户")
        store.ensure_token_account("test_user")
        from comedy_agent.auth.router import create_access_token
        token = create_access_token({"sub": "test_user"})

        with TestClient(app) as c:
            c.headers["Authorization"] = f"Bearer {token}"
            yield c

        state.memory = None
        state.orch = None


class TestSpeedAPI:
    """极速版 API 测试。"""

    def test_estimate_tokens(self, client):
        """Token 预估接口。"""
        res = client.post("/speed/estimate", json={"text": "这款防晒霜防水效果很好"})
        assert res.status_code == 200
        data = res.json()
        assert data["estimated_tokens"] > 0
        assert "estimated_cost" in data

    def test_polish_without_role(self, client):
        """无 IP 角色的趣味加工。"""
        res = client.post("/speed/polish", json={
            "text": "这款防晒霜防水效果很好",
            "intensity": "medium",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["original"] == "这款防晒霜防水效果很好"
        assert "polished" in data
        assert data["ip_role"] is None
        assert data["token_cost"] == 20

    def test_polish_with_role(self, client):
        """选择 IP 角色的趣味加工。"""
        # 先创建一个 IP 角色
        from comedy_agent.memory.models import IPStyleData
        role = IPStyleData(
            actor_name="李诞",
            description="李诞式吐槽风格",
            prompt_snippet="用李诞式自嘲、夸张比喻的语气",
            version="1.0",
            avatar_url="http://example.com/avatar.jpg",
            profile_url="/ip/lidan",
        )
        role = state.memory.save_ip_style(role)

        res = client.post("/speed/polish", json={
            "text": "加班到凌晨，好累",
            "intensity": "medium",
            "ip_role_id": role.style_id,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["ip_role"] is not None
        assert data["ip_role"]["actor_name"] == "李诞"
        assert data["ip_role"]["avatar_url"] is not None
        assert data["ip_role"]["profile_url"] == "/ip/lidan"

    def test_polish_insufficient_tokens(self, client):
        """余额不足返回 402。"""
        state.memory.deduct_tokens("test_user", 5000)  # 扣光余额
        res = client.post("/speed/polish", json={
            "text": "测试文本",
            "intensity": "medium",
        })
        assert res.status_code == 402
