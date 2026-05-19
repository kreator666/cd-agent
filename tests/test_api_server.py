"""FastAPI HTTP 服务单元测试。"""

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
    """提供 TestClient（ lifespan 自动执行，memory 使用内存数据库）。"""
    with patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ), patch(
        "comedy_agent.api.server.AgentOrchestrator"
    ) as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch.list_skills.return_value = ["standup_generator"]
        mock_orch_cls.return_value = mock_orch

        # 使用 TestClient 让 lifespan 自动运行
        with TestClient(app) as c:
            # lifespan 已经执行完毕，替换 memory 为内存数据库实例
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
            yield c

    # 清理
    state.orch = None
    state.memory = None


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestSkills:
    def test_list_skills(self, client):
        response = client.get("/skills")
        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
        assert "standup_generator" in data["skills"]


class TestChat:
    def test_chat_success(self, client):
        # TestClient  lifespan 里的 mock 已经替换了 state.orch
        # 但我们需要让它能返回正常结果
        from comedy_agent.api.server import state

        state.orch.run = MagicMock(
            return_value={
                "output": "Agent 回答",
                "messages": [
                    MagicMock(type="human", content="你好"),
                    MagicMock(type="ai", content="Agent 回答"),
                ],
            }
        )

        response = client.post(
            "/chat",
            json={"prompt": "你好"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["output"] == "Agent 回答"
        assert len(data["messages"]) == 2

    def test_chat_with_history(self, client):
        from comedy_agent.api.server import state

        state.orch.run = MagicMock(
            return_value={
                "output": "好的",
                "messages": [],
            }
        )

        response = client.post(
            "/chat",
            json={
                "prompt": "继续",
                "chat_history": [["human", "上一句"], ["ai", "上一答"]],
            },
        )
        assert response.status_code == 200
        _, call_kwargs = state.orch.run.call_args
        assert call_kwargs["chat_history"] == [
            ("human", "上一句"),
            ("ai", "上一答"),
        ]


class TestStandupSkill:
    def test_standup_skill(self, client):
        with patch(
            "comedy_agent.api.server.StandupSkill"
        ) as mock_skill_cls:
            mock_skill = MagicMock()
            mock_skill.invoke.return_value = "生成的段子"
            mock_skill_cls.return_value = mock_skill

            response = client.post(
                "/skills/standup",
                json={
                    "topic": "相亲",
                    "style": "自嘲",
                    "duration": 3,
                    "audience": "年轻人",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["content"] == "生成的段子"


class TestFeedbackIngest:
    """高评分内容回流端点测试。"""

    def test_feedback_ingest_success(self, client):
        with patch("comedy_agent.api.server.FeedbackLoop") as mock_loop_cls:
            mock_loop = MagicMock()
            mock_loop.ingest_high_rated_scripts.return_value = {
                "ingested_scripts": 2,
                "total_chunks": 5,
                "script_ids": ["s1", "s2"],
                "skipped": [],
                "dry_run": False,
            }
            mock_loop_cls.return_value = mock_loop

            response = client.post(
                "/feedback/ingest",
                json={"min_rating": 4.0, "chunk_strategy": "paragraph"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ingested_scripts"] == 2
            assert data["total_chunks"] == 5
            assert data["dry_run"] is False
            mock_loop_cls.assert_called_once()
            call_kwargs = mock_loop_cls.call_args[1]
            assert call_kwargs["min_rating"] == 4.0

    def test_feedback_ingest_dry_run(self, client):
        with patch("comedy_agent.api.server.FeedbackLoop") as mock_loop_cls:
            mock_loop = MagicMock()
            mock_loop.ingest_high_rated_scripts.return_value = {
                "ingested_scripts": 0,
                "total_chunks": 0,
                "script_ids": [],
                "skipped": [],
                "dry_run": True,
            }
            mock_loop_cls.return_value = mock_loop

            response = client.post(
                "/feedback/ingest",
                json={"dry_run": True, "min_rating": 4.0},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["dry_run"] is True

    def test_feedback_ingest_memory_not_ready(self, client):
        state.memory = None
        response = client.post(
            "/feedback/ingest",
            json={"min_rating": 4.0},
        )
        assert response.status_code == 503
