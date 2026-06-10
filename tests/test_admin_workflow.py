"""测试 admin 工作流配置 API。"""

import json
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

    def test_get_workflow_success(self):
        """admin 可以获取工作流配置。"""
        res = client.get("/admin/workflow", headers=_admin_headers())
        assert res.status_code == 200
        data = res.json()
        assert "steps" in data
        assert len(data["steps"]) > 0
        # 验证默认步骤结构
        first = data["steps"][0]
        assert first["id"] == "outline_check"
        assert first["type"] == "validation"

    def test_update_workflow_requires_admin(self):
        """非 admin 无法更新工作流配置。"""
        res = client.put(
            "/admin/workflow",
            headers=_user_headers(),
            json={"steps": [{"id": "test", "type": "skill", "message": "test"}]},
        )
        assert res.status_code == 403

    def test_update_workflow_validation(self):
        """更新工作流时校验步骤结构。"""
        # 缺少 id（Pydantic 会返回 422）
        res = client.put(
            "/admin/workflow",
            headers=_admin_headers(),
            json={"steps": [{"type": "skill", "message": "test"}]},
        )
        assert res.status_code == 422

        # 非法 type（代码手动校验返回 400）
        res = client.put(
            "/admin/workflow",
            headers=_admin_headers(),
            json={"steps": [{"id": "test", "type": "invalid", "message": "test"}]},
        )
        assert res.status_code == 400

    def test_update_workflow_success(self):
        """admin 可以成功更新工作流配置。"""
        new_steps = [
            {
                "id": "outline_check",
                "type": "validation",
                "field": "outline",
                "message": "test outline",
            },
            {
                "id": "genre_select",
                "type": "selection",
                "skill_type": "genre",
                "message": "test genre",
            },
        ]
        res = client.put("/admin/workflow", headers=_admin_headers(), json={"steps": new_steps})
        assert res.status_code == 200
        assert res.json()["success"] is True

        # 验证已更新
        res = client.get("/admin/workflow", headers=_admin_headers())
        assert res.status_code == 200
        data = res.json()
        assert len(data["steps"]) == 2
        assert data["steps"][0]["message"] == "test outline"

        # 恢复默认配置
        default_steps = [
            {
                "id": "outline_check",
                "type": "validation",
                "field": "outline",
                "message": "📋 请先设置选题大纲。请描述你想要创作的核心内容，例如：实习生被领导刁难后逆袭的职场段子。",
            },
            {
                "id": "genre_select",
                "type": "selection",
                "skill_type": "genre",
                "message": "🎭 请选择剧本体裁，这将决定整体的创作风格。",
            },
            {
                "id": "step_topic",
                "type": "skill",
                "skill": "topic",
                "message": "🔍 正在调用话题专家扩写话题背景与冲突点...",
                "requires_selection": True,
                "selection_skill_type": "topic",
            },
            {
                "id": "step_attitude",
                "type": "skill",
                "skill": "attitude",
                "message": "🎯 正在调用态度专家注入态度...",
                "requires_selection": True,
                "selection_skill_type": "attitude",
            },
            {
                "id": "step_emotion",
                "type": "skill",
                "skill": "emotion",
                "message": "💫 正在调用情绪专家调整情绪节奏...",
                "requires_selection": True,
                "selection_skill_type": "emotion",
            },
            {
                "id": "step_rule_persona",
                "type": "skill",
                "skill": "rule_persona",
                "message": "🎭 正在应用人物画像规则...",
                "requires_selection": False,
            },
            {
                "id": "step_composer",
                "type": "skill",
                "skill": "script_composer",
                "message": "📝 正在调用剧本编排专家生成最终剧本...",
                "is_final": True,
            },
        ]
        res = client.put("/admin/workflow", headers=_admin_headers(), json={"steps": default_steps})
        assert res.status_code == 200
