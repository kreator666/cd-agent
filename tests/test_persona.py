"""人物画像 CRUD 测试。"""

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
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore
        store = SQLMemoryStore(db_url="sqlite:///:memory:")
        state.memory = store
        state.orch = mock_orch

        store.save_user_profile("test_user", "测试用户")
        store.ensure_token_account("test_user")
        from comedy_agent.auth.router import create_access_token
        token = create_access_token({"sub": "test_user"})

        with TestClient(app) as c:
            c.headers["Authorization"] = f"Bearer {token}"
            yield c

        state.memory = None
        state.orch = None


class TestPersonaAPI:
    """人物画像 API 测试。"""

    def test_create_persona(self, client):
        """创建人物画像。"""
        res = client.post("/pro/personas", json={
            "name": "毒舌职场侠",
            "rule_content": {
                "prefer_short_sentence": True,
                "forbidden_words": ["绝对", "垃圾"],
                "sentence_pace": "fast",
                "opening_hook": True,
            },
        })
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "毒舌职场侠"
        assert data["creator_id"] == "test_user"
        assert data["rule_content"]["prefer_short_sentence"] is True
        assert data["is_active"] is True

    def test_list_personas(self, client):
        """列出人物画像。"""
        client.post("/pro/personas", json={"name": "画像A", "rule_content": {}})
        client.post("/pro/personas", json={"name": "画像B", "rule_content": {}})
        res = client.get("/pro/personas")
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 2

    def test_get_persona(self, client):
        """获取人物画像详情。"""
        create_res = client.post("/pro/personas", json={"name": "测试画像", "rule_content": {}})
        pid = create_res.json()["persona_id"]
        res = client.get(f"/pro/personas/{pid}")
        assert res.status_code == 200
        assert res.json()["name"] == "测试画像"

    def test_update_persona(self, client):
        """更新人物画像。"""
        create_res = client.post("/pro/personas", json={"name": "旧名称", "rule_content": {}})
        pid = create_res.json()["persona_id"]
        res = client.put(f"/pro/personas/{pid}", json={"name": "新名称"})
        assert res.status_code == 200
        assert res.json()["name"] == "新名称"

    def test_delete_persona(self, client):
        """删除人物画像。"""
        create_res = client.post("/pro/personas", json={"name": "待删除", "rule_content": {}})
        pid = create_res.json()["persona_id"]
        res = client.delete(f"/pro/personas/{pid}")
        assert res.status_code == 200
        assert res.json()["success"] is True
