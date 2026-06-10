"""测试 admin 工作流配置 API 和状态机迁移。"""

import pytest
from fastapi.testclient import TestClient

from comedy_agent.api.server import app
from comedy_agent.auth.security import create_access_token

client = TestClient(app)


def _admin_headers():
    token = create_access_token("admin")
    return {"Authorization": f"Bearer {token}"}


def _user_headers():
    token = create_access_token("user1")
    return {"Authorization": f"Bearer {token}"}


class TestAdminWorkflow:
    """Admin 工作流配置接口测试。"""

    def test_get_workflow_requires_admin(self):
        """非 admin 无法获取工作流配置。"""
        res = client.get("/admin/workflow", headers=_user_headers())
        assert res.status_code == 403

    def test_get_workflow_returns_state_machine(self):
        """admin 可以获取状态机格式的工作流配置。"""
        res = client.get("/admin/workflow", headers=_admin_headers())
        assert res.status_code == 200
        data = res.json()
        assert "initial_state" in data
        assert "states" in data
        assert "transitions" in data
        assert isinstance(data["states"], dict)

    def test_update_workflow_requires_admin(self):
        """非 admin 无法更新工作流配置。"""
        res = client.put(
            "/admin/workflow",
            headers=_user_headers(),
            json={
                "initial_state": "s1",
                "states": {"s1": {"action": "collect", "slot": "x", "message": "test"}},
                "transitions": {"s1": {"next": None}},
            },
        )
        assert res.status_code == 403

    def test_update_workflow_validation(self):
        """更新工作流时校验状态机结构。"""
        # initial_state 不存在
        res = client.put(
            "/admin/workflow",
            headers=_admin_headers(),
            json={
                "initial_state": "missing",
                "states": {"s1": {"action": "collect", "slot": "x", "message": "test"}},
                "transitions": {"s1": {"next": None}},
            },
        )
        assert res.status_code == 400

        # action 非法
        res = client.put(
            "/admin/workflow",
            headers=_admin_headers(),
            json={
                "initial_state": "s1",
                "states": {"s1": {"action": "invalid", "message": "test"}},
                "transitions": {"s1": {"next": None}},
            },
        )
        assert res.status_code == 400

        # collect 缺少 slot
        res = client.put(
            "/admin/workflow",
            headers=_admin_headers(),
            json={
                "initial_state": "s1",
                "states": {"s1": {"action": "collect", "message": "test"}},
                "transitions": {"s1": {"next": None}},
            },
        )
        assert res.status_code == 400

        # 缺少 transition
        res = client.put(
            "/admin/workflow",
            headers=_admin_headers(),
            json={
                "initial_state": "s1",
                "states": {
                    "s1": {"action": "collect", "slot": "x", "message": "test"},
                    "s2": {"action": "aggregate", "message": "done"},
                },
                "transitions": {"s1": {"next": "s2"}},
            },
        )
        assert res.status_code == 400

    def test_update_workflow_success(self):
        """admin 可以成功更新工作流配置。"""
        new_config = {
            "initial_state": "collect_outline",
            "states": {
                "collect_outline": {"action": "collect", "slot": "outline", "message": "test outline"},
                "pick_genre": {"action": "select", "skill_type": "genre", "message": "test genre"},
                "final": {"action": "aggregate", "message": "test final"},
            },
            "transitions": {
                "collect_outline": {"next": "pick_genre"},
                "pick_genre": {"next": "final"},
                "final": {"next": None},
            },
        }
        res = client.put("/admin/workflow", headers=_admin_headers(), json=new_config)
        assert res.status_code == 200
        assert res.json()["success"] is True

        # 验证已更新
        res = client.get("/admin/workflow", headers=_admin_headers())
        assert res.status_code == 200
        data = res.json()
        assert data["initial_state"] == "collect_outline"
        assert data["states"]["collect_outline"]["message"] == "test outline"
        assert data["transitions"]["collect_outline"]["next"] == "pick_genre"

        # 恢复默认配置
        default_config = {
            "initial_state": "awaiting_outline",
            "states": {
                "awaiting_outline": {"action": "collect", "slot": "outline", "message": "请告诉我你想创作什么内容？"},
                "awaiting_genre": {"action": "select", "skill_type": "genre", "message": "请选择剧本体裁"},
                "calling_topic": {"action": "call", "skill": "topic", "message": "调用话题专家"},
                "calling_attitude": {"action": "call", "skill": "attitude", "message": "调用态度专家"},
                "calling_emotion": {"action": "call", "skill": "emotion", "message": "调用情绪专家"},
                "calling_rule_persona": {"action": "call", "skill": "rule_persona", "message": "应用人物画像"},
                "aggregating": {"action": "aggregate", "message": "生成最终剧本"},
            },
            "transitions": {
                "awaiting_outline": {"next": "awaiting_genre"},
                "awaiting_genre": {"next": "calling_topic"},
                "calling_topic": {"next": "calling_attitude"},
                "calling_attitude": {"next": "calling_emotion"},
                "calling_emotion": {"next": "calling_rule_persona"},
                "calling_rule_persona": {"next": "aggregating"},
                "aggregating": {"next": None},
            },
        }
        res = client.put("/admin/workflow", headers=_admin_headers(), json=default_config)
        assert res.status_code == 200


class TestWorkflowMigration:
    """测试旧版工作流配置自动迁移到状态机。"""

    def test_legacy_steps_migration(self):
        """旧版步骤列表自动迁移为状态机。"""
        from comedy_agent.api.routers.pro_workflow import _migrate_legacy_workflow

        legacy = [
            {"id": "outline_check", "type": "validation", "field": "outline", "message": "m1"},
            {"id": "genre_select", "type": "selection", "skill_type": "genre", "message": "m2"},
            {"id": "step_topic", "type": "skill", "skill": "topic", "message": "m3"},
            {"id": "step_composer", "type": "skill", "skill": "script_composer", "is_final": True, "message": "m4"},
        ]

        result = _migrate_legacy_workflow(legacy)
        assert result["initial_state"] == "outline_check"
        assert result["states"]["outline_check"]["action"] == "collect"
        assert result["states"]["outline_check"]["slot"] == "outline"
        assert result["states"]["genre_select"]["action"] == "select"
        assert result["states"]["genre_select"]["skill_type"] == "genre"
        assert result["states"]["step_topic"]["action"] == "call"
        assert result["states"]["step_topic"]["skill"] == "topic"
        assert result["states"]["step_composer"]["action"] == "aggregate"
        assert result["transitions"]["step_composer"]["next"] is None
        assert result["transitions"]["outline_check"]["next"] == "genre_select"

    def test_new_schema_passthrough(self):
        """新版 schema 直接透传。"""
        from comedy_agent.api.routers.pro_workflow import _migrate_legacy_workflow

        modern = {
            "initial_state": "s1",
            "states": {"s1": {"action": "collect", "slot": "x", "message": "test"}},
            "transitions": {"s1": {"next": None}},
        }
        result = _migrate_legacy_workflow(modern)
        assert result == modern
