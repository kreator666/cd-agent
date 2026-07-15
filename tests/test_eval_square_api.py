"""测试段子广场相关 API。"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from comedy_agent.api.server import app, state
from datetime import datetime

from comedy_agent.memory.schema import EvalResult, EvalSession, JokeComment, JokeRating, UserProfile


def _patched_create_engine(*args, **kwargs):
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


def _register_and_login(client: TestClient, user_id: str, password: str = "testpass"):
    client.post("/auth/register", json={"user_id": user_id, "password": password})
    resp = client.post("/auth/login", json={"user_id": user_id, "password": password})
    return resp.json()["access_token"]


def _create_done_result(user_id: str, content: str = "测试段子内容") -> str:
    """在数据库里直接创建一个已完成的 EvalResult，返回 result_id。"""
    db: Session = state.memory._store._new_session()
    # 确保用户画像存在，便于广场列表 join 查询
    user = db.query(UserProfile).filter_by(user_id=user_id).first()
    if user is None:
        db.add(UserProfile(user_id=user_id, nickname=f"用户{user_id}"))
        db.commit()
    session_id = "sess_test_01"
    result_id = "res_test_01"
    db.add(
        EvalSession(
            session_id=session_id,
            user_id=user_id,
            skill_name="standup",
            model="deepseek-v3",
            topic="测试话题",
            attitude="调侃",
            bias="无",
            emotion="轻松",
            duration=3,
            status="done",
            total=1,
        )
    )
    db.add(
        EvalResult(
            result_id=result_id,
            session_id=session_id,
            section_id="combo_a",
            section_title="组合：A",
            section_body="A body",
            combo_id="combo_a",
            combo_sections=[{"id": "a", "title": "A"}],
            content=content,
            status="done",
            model="deepseek-v3",
            rating="top",
        )
    )
    db.commit()
    db.close()
    return result_id


@pytest.fixture
def client():
    """提供已认证的 TestClient，memory 使用内存数据库。"""
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
        mock_orch.run.return_value = {"output": "测试", "messages": []}
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore

        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store

        with TestClient(app) as c:
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")

            token = _register_and_login(c, "author")
            with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as authed_c:
                state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
                yield authed_c

    state.orch = None
    state.memory = None


def _other_client(user_id: str = "other") -> TestClient:
    """在测试函数内创建另一个已认证用户 client。

    必须在 ``client`` fixture 提供的 patch 上下文中调用。
    """
    token = _register_and_login(TestClient(app), user_id)
    db: Session = state.memory._store._new_session()
    if db.query(UserProfile).filter_by(user_id=user_id).first() is None:
        db.add(UserProfile(user_id=user_id, nickname=f"用户{user_id}"))
        db.commit()
    db.close()
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


class TestPublish:
    """发布/取消发布测试。"""

    def test_publish_success(self, client):
        result_id = _create_done_result("author")
        resp = client.post(f"/eval/results/{result_id}/publish")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # 列表中可见
        resp = client.get("/eval/square?sort=newest")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["jokes"]) == 1
        assert data["jokes"][0]["result_id"] == result_id
        assert data["jokes"][0]["author_score"] == 8.0

    def test_publish_already_published(self, client):
        result_id = _create_done_result("author")
        client.post(f"/eval/results/{result_id}/publish")
        resp = client.post(f"/eval/results/{result_id}/publish")
        assert resp.status_code == 400
        assert "已经发布" in resp.json()["detail"]

    def test_publish_only_done(self, client):
        db: Session = state.memory._store._new_session()
        db.add(
            EvalSession(
                session_id="sess_pending",
                user_id="author",
                skill_name="standup",
                model="deepseek-v3",
                topic="测试话题",
                attitude="调侃",
                bias="无",
                emotion="轻松",
                duration=3,
                status="running",
                total=1,
            )
        )
        db.add(
            EvalResult(
                result_id="res_pending",
                session_id="sess_pending",
                section_id="combo_a",
                section_title="组合：A",
                section_body="A body",
                status="pending",
                model="deepseek-v3",
            )
        )
        db.commit()
        db.close()

        resp = client.post("/eval/results/res_pending/publish")
        assert resp.status_code == 400
        assert "只能发布已生成完成" in resp.json()["detail"]

    def test_unpublish_success(self, client):
        result_id = _create_done_result("author")
        client.post(f"/eval/results/{result_id}/publish")
        resp = client.delete(f"/eval/results/{result_id}/publish")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        resp = client.get("/eval/square?sort=newest")
        assert resp.json()["jokes"] == []

    def test_other_cannot_unpublish(self, client):
        result_id = _create_done_result("author")
        client.post(f"/eval/results/{result_id}/publish")

        resp = _other_client().delete(f"/eval/results/{result_id}/publish")
        assert resp.status_code == 404


class TestPublicRate:
    """路人评分测试。"""

    def test_rate_and_update(self, client):
        result_id = _create_done_result("author")
        client.post(f"/eval/results/{result_id}/publish")

        resp = _other_client().post(f"/eval/square/{result_id}/rate", json={"score": 8})
        assert resp.status_code == 200
        data = resp.json()
        assert data["average_score"] == 8.0
        assert data["rating_count"] == 1

        # 更新评分
        resp = _other_client().post(f"/eval/square/{result_id}/rate", json={"score": 6})
        assert resp.status_code == 200
        data = resp.json()
        assert data["average_score"] == 6.0
        assert data["rating_count"] == 1

    def test_author_cannot_rate_self(self, client):
        result_id = _create_done_result("author")
        client.post(f"/eval/results/{result_id}/publish")

        resp = client.post(f"/eval/square/{result_id}/rate", json={"score": 10})
        assert resp.status_code == 400
        assert "不能给自己的段子打分" in resp.json()["detail"]

    def test_rate_out_of_range(self, client):
        result_id = _create_done_result("author")
        client.post(f"/eval/results/{result_id}/publish")

        resp = _other_client().post(f"/eval/square/{result_id}/rate", json={"score": 11})
        assert resp.status_code == 422

    def test_rate_unpublished(self, client):
        result_id = _create_done_result("author")
        # 未发布
        resp = _other_client().post(f"/eval/square/{result_id}/rate", json={"score": 5})
        assert resp.status_code == 404


class TestComments:
    """点评测试。"""

    def test_post_and_list(self, client):
        result_id = _create_done_result("author")
        client.post(f"/eval/results/{result_id}/publish")

        resp = _other_client().post(
            f"/eval/square/{result_id}/comments", json={"content": "  这梗绝了！  "}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "这梗绝了！"
        assert data["user_id"] == "other"

        resp = client.get(f"/eval/square/{result_id}/comments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["comments"]) == 1

    def test_empty_content(self, client):
        result_id = _create_done_result("author")
        client.post(f"/eval/results/{result_id}/publish")

        resp = _other_client().post(f"/eval/square/{result_id}/comments", json={"content": "  "})
        assert resp.status_code == 422


class TestSquareList:
    """广场列表排序测试。"""

    def test_newest_sort(self, client):
        _create_done_result("author", content="old")
        # 手动创建第二个结果并发布
        db: Session = state.memory._store._new_session()
        db.add(
            EvalSession(
                session_id="sess_02",
                user_id="author",
                skill_name="standup",
                model="deepseek-v3",
                topic="测试话题2",
                attitude="调侃",
                bias="无",
                emotion="轻松",
                duration=3,
                status="done",
                total=1,
            )
        )
        db.add(
            EvalResult(
                result_id="res_02",
                session_id="sess_02",
                section_id="combo_b",
                section_title="组合：B",
                section_body="B body",
                content="new",
                status="done",
                model="deepseek-v3",
                is_published=True,
                rating="ok",
                published_at=datetime(2026, 7, 15, 12, 0, 0),
            )
        )
        db.commit()
        db.close()

        resp = client.get("/eval/square?sort=newest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["jokes"][0]["result_id"] == "res_02"

    def test_hottest_sort(self, client):
        result_id = _create_done_result("author", content="hot joke")
        client.post(f"/eval/results/{result_id}/publish")
        _other_client().post(f"/eval/square/{result_id}/rate", json={"score": 10})
        _other_client().post(f"/eval/square/{result_id}/comments", json={"content": "火！"})

        # 创建一个无人问津的段子
        db: Session = state.memory._store._new_session()
        db.add(
            EvalSession(
                session_id="sess_cold",
                user_id="author",
                skill_name="standup",
                model="deepseek-v3",
                topic="cold",
                attitude="调侃",
                bias="无",
                emotion="轻松",
                duration=3,
                status="done",
                total=1,
            )
        )
        db.add(
            EvalResult(
                result_id="res_cold",
                session_id="sess_cold",
                section_id="combo_c",
                section_title="组合：C",
                section_body="C body",
                content="cold joke",
                status="done",
                model="deepseek-v3",
                is_published=True,
                rating="bad",
                published_at=datetime(2026, 7, 15, 10, 0, 0),
            )
        )
        db.commit()
        db.close()

        resp = client.get("/eval/square?sort=hottest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["jokes"][0]["result_id"] == result_id
