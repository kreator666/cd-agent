"""微信打赏功能测试。"""

from __future__ import annotations

from io import BytesIO
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
        mock_orch.run.return_value = {"output": "mocked", "messages": []}
        mock_orch.tools = []
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore

        store = SQLMemoryStore(db_url="sqlite:///:memory:")
        store.get_or_create_user("test_user", "测试用户")
        store.get_token_account("test_user")
        from comedy_agent.auth.security import create_access_token

        token = create_access_token("test_user")

        with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
            # lifespan 启动时会用 UnifiedMemory() 覆盖 state.memory，
            # 这里重新指回测试用的内存 store，确保用户数据存在。
            state.memory = store
            state.orch = mock_orch
            yield c

        state.memory = None
        state.orch = None


class TestTippingConfig:
    """/me/tipping-config 接口测试。"""

    def test_get_tipping_config_empty(self, client):
        """未配置时返回 null。"""
        resp = client.get("/me/tipping-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["qr_url"] is None
        assert data["tipping_copy"] is None

    def test_update_tipping_config(self, client):
        """上传二维码和文案后返回访问 URL。"""
        resp = client.post(
            "/me/tipping-config",
            data={"tipping_copy": "请作者喝奶茶 🧋"},
            files={"file": ("qr.png", BytesIO(b"fake-image-bytes"), "image/png")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["qr_url"] == "/static/qr_codes/test_user.png"
        assert data["tipping_copy"] == "请作者喝奶茶 🧋"

        # 再次 GET 应能取回
        resp = client.get("/me/tipping-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["qr_url"] == "/static/qr_codes/test_user.png"
        assert data["tipping_copy"] == "请作者喝奶茶 🧋"

    def test_update_tipping_config_without_file(self, client):
        """只更新文案时保留已有二维码。"""
        client.post(
            "/me/tipping-config",
            data={"tipping_copy": "先有二维码"},
            files={"file": ("qr.png", BytesIO(b"fake-image-bytes"), "image/png")},
        )
        resp = client.post(
            "/me/tipping-config",
            data={"tipping_copy": "只改文案"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["qr_url"] == "/static/qr_codes/test_user.png"
        assert data["tipping_copy"] == "只改文案"

    def test_update_tipping_config_rejects_non_image(self, client):
        """非图片上传应被拒绝。"""
        resp = client.post(
            "/me/tipping-config",
            data={"tipping_copy": ""},
            files={"file": ("qr.txt", BytesIO(b"not an image"), "text/plain")},
        )
        assert resp.status_code == 400
        assert "只允许上传图片" in resp.json()["detail"]

    def test_update_tipping_config_oversized_image(self, client):
        """超过 2MB 的图片应被拒绝。"""
        big = b"x" * (2 * 1024 * 1024 + 1)
        resp = client.post(
            "/me/tipping-config",
            data={"tipping_copy": ""},
            files={"file": ("qr.png", BytesIO(big), "image/png")},
        )
        assert resp.status_code == 400
        assert "不能超过 2MB" in resp.json()["detail"]
