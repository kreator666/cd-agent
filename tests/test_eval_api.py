"""笑果评测 API 测试。"""

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


def _mock_skill():
    """构造一个用于测试的 mock Skill。"""
    skill = MagicMock()
    skill.name = "standup_focused"
    skill.invoke.return_value = "这是生成的段子"
    return skill


@pytest.fixture
def client():
    with patch(
        "comedy_agent.memory.medium_term.create_engine", side_effect=_patched_create_engine
    ), patch("comedy_agent.api.server.AgentOrchestrator") as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch.run.return_value = {"output": "mocked", "messages": []}
        mock_orch.tools = []  # 让 eval 路由回退到 load_single_skill
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore
        store = SQLMemoryStore(db_url="sqlite:///:memory:")
        state.memory = store
        state.orch = mock_orch

        store.get_or_create_user("test_user", "测试用户")
        store.get_token_account("test_user")
        from comedy_agent.auth.security import create_access_token
        token = create_access_token("test_user")

        with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
            yield c

        state.memory = None
        state.orch = None


class TestEvalSections:
    """章节模板接口测试（保留但前端不再调用）。"""

    def test_get_sections(self, client):
        res = client.get("/eval/skills/standup/sections")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["skill_name"] == "standup"
        assert len(data["sections"]) == 10
        ids = [s["id"] for s in data["sections"]]
        assert "sec-1" in ids
        assert "sec-2" in ids
        assert "sec-10" in ids

    def test_get_sections_not_found(self, client):
        res = client.get("/eval/skills/nonexistent/sections")
        assert res.status_code == 404


class TestEvalSession:
    """评测会话接口测试。"""

    def test_create_session(self, client):
        with patch("comedy_agent.api.routers.eval.load_single_skill") as mock_load_skill:
            mock_load_skill.return_value = _mock_skill()

            res = client.post("/eval/sessions", json={
                "skill_name": "standup_focused",
                "model": "deepseek-v3",
                "topic": "骨折",
                "attitude": "自嘲",
                "bias": "无",
                "emotion": "荒诞",
            })
            assert res.status_code == 200, res.text
            data = res.json()
            assert data["total"] == 1
            assert data["status"] == "running"
            assert "session_id" in data

            # 立即查询会话
            session_id = data["session_id"]
            res2 = client.get(f"/eval/sessions/{session_id}")
            assert res2.status_code == 200, res2.text
            detail = res2.json()
            assert detail["total"] == 1
            assert len(detail["results"]) == 1
            assert detail["results"][0]["section_id"] == "full"

    def test_create_session_missing_input(self, client):
        res = client.post("/eval/sessions", json={
            "skill_name": "standup_focused",
            "model": "deepseek-v3",
            "topic": "",
            "attitude": "",
            "bias": "无",
            "emotion": "",
        })
        assert res.status_code == 400

    def test_get_session_not_found(self, client):
        res = client.get("/eval/sessions/notexist")
        assert res.status_code == 404


class TestEvalRate:
    """评分接口测试。"""

    def test_rate_result(self, client):
        with patch("comedy_agent.api.routers.eval.load_single_skill") as mock_load_skill:
            mock_load_skill.return_value = _mock_skill()

            res = client.post("/eval/sessions", json={
                "skill_name": "standup_focused",
                "model": "deepseek-v3",
                "topic": "骨折",
                "attitude": "自嘲",
                "bias": "无",
                "emotion": "荒诞",
            })
            session_id = res.json()["session_id"]

            detail = client.get(f"/eval/sessions/{session_id}").json()
            result_id = detail["results"][0]["id"]

            rate_res = client.post(f"/eval/results/{result_id}/rate", json={"rating": "top"})
            assert rate_res.status_code == 200
            assert rate_res.json()["success"] is True

            detail2 = client.get(f"/eval/sessions/{session_id}").json()
            assert detail2["rated"] == 1
            assert detail2["top_count"] == 1

    def test_rate_invalid(self, client):
        res = client.post("/eval/results/any/rate", json={"rating": "invalid"})
        assert res.status_code == 400


class TestEvalList:
    """会话列表接口测试。"""

    def test_list_sessions(self, client):
        with patch("comedy_agent.api.routers.eval.load_single_skill") as mock_load_skill:
            mock_load_skill.return_value = _mock_skill()

            client.post("/eval/sessions", json={
                "skill_name": "standup_focused",
                "model": "deepseek-v3",
                "topic": "骨折",
                "attitude": "自嘲",
                "bias": "无",
                "emotion": "荒诞",
            })

            res = client.get("/eval/sessions")
            assert res.status_code == 200
            data = res.json()
            assert len(data["sessions"]) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
