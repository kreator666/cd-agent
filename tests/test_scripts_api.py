"""作品管理 API 单元测试。"""

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
    """提供 TestClient，memory 使用内存数据库。"""
    with patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ), patch(
        "comedy_agent.api.server.AgentOrchestrator"
    ) as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch.list_skills.return_value = ["standup_generator"]
        mock_orch_cls.return_value = mock_orch

        with TestClient(app) as c:
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
            yield c

    state.orch = None
    state.memory = None


class TestCreateScript:
    """创建作品测试。"""

    def test_create_script_success(self, client):
        response = client.post(
            "/scripts",
            json={
                "user_id": "u001",
                "title": "职场脱口秀",
                "content": "今天讲加班...",
                "script_type": "standup",
                "tags": ["职场", "加班"],
                "rating": 4.5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "职场脱口秀"
        assert data["content"] == "今天讲加班..."
        assert data["script_type"] == "standup"
        assert data["tags"] == ["职场", "加班"]
        assert data["rating"] == 4.5
        assert data["script_id"] is not None

    def test_create_script_minimal(self, client):
        response = client.post(
            "/scripts",
            json={"user_id": "u002", "content": "只有内容"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "只有内容"
        assert data["title"] is None

    def test_create_script_memory_not_ready(self, client):
        state.memory = None
        response = client.post(
            "/scripts",
            json={"user_id": "u003", "content": "test"},
        )
        assert response.status_code == 503


class TestListScripts:
    """列出作品测试。"""

    def test_list_scripts_empty(self, client):
        response = client.get("/scripts?user_id=u010")
        assert response.status_code == 200
        data = response.json()
        assert data["scripts"] == []

    def test_list_scripts_with_data(self, client):
        # 先创建两条
        client.post(
            "/scripts",
            json={
                "user_id": "u011",
                "title": "A",
                "content": "a",
                "script_type": "standup",
            },
        )
        client.post(
            "/scripts",
            json={
                "user_id": "u011",
                "title": "B",
                "content": "b",
                "script_type": "sketch",
            },
        )
        response = client.get("/scripts?user_id=u011")
        assert response.status_code == 200
        data = response.json()
        assert len(data["scripts"]) == 2

    def test_list_scripts_filter_by_type(self, client):
        client.post(
            "/scripts",
            json={
                "user_id": "u012",
                "title": "A",
                "content": "a",
                "script_type": "standup",
            },
        )
        client.post(
            "/scripts",
            json={
                "user_id": "u012",
                "title": "B",
                "content": "b",
                "script_type": "sketch",
            },
        )
        response = client.get("/scripts?user_id=u012&script_type=standup")
        assert response.status_code == 200
        data = response.json()
        assert len(data["scripts"]) == 1
        assert data["scripts"][0]["script_type"] == "standup"

    def test_list_scripts_memory_not_ready(self, client):
        state.memory = None
        response = client.get("/scripts?user_id=u013")
        assert response.status_code == 503


class TestGetScript:
    """获取作品详情测试。"""

    def test_get_script_success(self, client):
        create_resp = client.post(
            "/scripts",
            json={"user_id": "u020", "title": "Test", "content": "content"},
        )
        script_id = create_resp.json()["script_id"]

        response = client.get(f"/scripts/{script_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["script"]["title"] == "Test"

    def test_get_script_not_found(self, client):
        response = client.get("/scripts/nonexistent")
        assert response.status_code == 404

    def test_get_script_memory_not_ready(self, client):
        state.memory = None
        response = client.get("/scripts/some-id")
        assert response.status_code == 503


class TestUpdateScript:
    """更新作品测试。"""

    def test_update_script_success(self, client):
        create_resp = client.post(
            "/scripts",
            json={"user_id": "u030", "title": "Old", "content": "old"},
        )
        script_id = create_resp.json()["script_id"]

        response = client.put(
            f"/scripts/{script_id}",
            json={"user_id": "u030", "title": "New", "content": "new"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New"
        assert data["content"] == "new"
        assert data["script_id"] == script_id

    def test_update_script_partial(self, client):
        create_resp = client.post(
            "/scripts",
            json={
                "user_id": "u031",
                "title": "Title",
                "content": "Content",
                "script_type": "standup",
            },
        )
        script_id = create_resp.json()["script_id"]

        response = client.put(
            f"/scripts/{script_id}",
            json={"user_id": "u031", "title": "New Title"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"
        assert data["content"] == "Content"
        assert data["script_type"] == "standup"

    def test_update_script_not_found(self, client):
        response = client.put(
            "/scripts/nonexistent",
            json={"user_id": "u032", "title": "X"},
        )
        assert response.status_code == 404

    def test_update_script_memory_not_ready(self, client):
        state.memory = None
        response = client.put(
            "/scripts/some-id",
            json={"user_id": "u033", "title": "X"},
        )
        assert response.status_code == 503


class TestDeleteScript:
    """删除作品测试。"""

    def test_delete_script_success(self, client):
        create_resp = client.post(
            "/scripts",
            json={"user_id": "u040", "title": "Delete Me", "content": "x"},
        )
        script_id = create_resp.json()["script_id"]

        response = client.delete(f"/scripts/{script_id}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 确认已删除
        get_resp = client.get(f"/scripts/{script_id}")
        assert get_resp.status_code == 404

    def test_delete_script_not_found(self, client):
        response = client.delete("/scripts/nonexistent")
        assert response.status_code == 404

    def test_delete_script_memory_not_ready(self, client):
        state.memory = None
        response = client.delete("/scripts/some-id")
        assert response.status_code == 503


class TestRateScript:
    """作品评分测试。"""

    def test_rate_script_success(self, client):
        create_resp = client.post(
            "/scripts",
            json={"user_id": "u050", "title": "Rate Me", "content": "x"},
        )
        script_id = create_resp.json()["script_id"]

        response = client.patch(
            f"/scripts/{script_id}/rate",
            json={"rating": 4.8},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        # 确认评分生效
        get_resp = client.get(f"/scripts/{script_id}")
        assert get_resp.json()["script"]["rating"] == 4.8

    def test_rate_script_not_found(self, client):
        response = client.patch(
            "/scripts/nonexistent/rate",
            json={"rating": 5.0},
        )
        assert response.status_code == 404

    def test_rate_script_memory_not_ready(self, client):
        state.memory = None
        response = client.patch(
            "/scripts/some-id/rate",
            json={"rating": 3.0},
        )
        assert response.status_code == 503
