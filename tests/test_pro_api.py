"""专业版 API 测试。"""

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
        mock_orch.run.return_value = {"output": "## 场景1\n\n**场景**：公司大厅 / 白天\n\n对白：...", "messages": []}
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore
        store = SQLMemoryStore(db_url="sqlite:///:memory:")
        state.memory = store
        state.orch = mock_orch

        store.save_user_profile("test_user", "测试用户")
        store.ensure_token_account("test_user")
        store.recharge_tokens("test_user", 10000)
        from comedy_agent.auth.router import create_access_token
        token = create_access_token({"sub": "test_user"})

        with TestClient(app) as c:
            c.headers["Authorization"] = f"Bearer {token}"
            yield c

        state.memory = None
        state.orch = None


class TestProAPI:
    """专业版 API 测试。"""

    def test_generate_without_persona(self, client):
        """无人物画像时返回引导信息。"""
        res = client.post("/pro/generate", json={
            "outline": "实习生被领导刁难后逆袭",
            "persona_id": "nonexistent",
            "skill_ids": ["topic"],
        })
        assert res.status_code == 400
        assert "人物画像" in res.json()["detail"]

    def test_generate_with_persona(self, client):
        """有人物画像时正常生成。"""
        # 创建画像
        persona_res = client.post("/pro/personas", json={
            "name": "冷峻短剧画像",
            "rule_content": {
                "prefer_short_sentence": True,
                "sentence_pace": "fast",
                "opening_hook": True,
            },
        })
        persona_id = persona_res.json()["persona_id"]

        res = client.post("/pro/generate", json={
            "outline": "实习生被领导刁难后逆袭",
            "persona_id": persona_id,
            "skill_ids": ["topic", "attitude"],
            "confirm_budget": True,
        })
        assert res.status_code == 200
        data = res.json()
        assert "script" in data
        assert data["persona_name"] == "冷峻短剧画像"

    def test_estimate_budget_warning(self, client):
        """预算告警。"""
        res = client.post("/pro/estimate", json={
            "outline": "a" * 2000,  # 长文本触发告警
            "skill_ids": ["topic", "attitude", "emotion", "genre", "script_composer"],
        })
        assert res.status_code == 200
        data = res.json()
        assert data["budget_warning"] is True

    def test_list_pro_skills(self, client):
        """列出专业版可用 Skill。"""
        res = client.get("/pro/skills")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
