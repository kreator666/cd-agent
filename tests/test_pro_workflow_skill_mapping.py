"""ProWorkflowEngine 中文 Skill mention 映射测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from comedy_agent.api.routers.pro_workflow import ProWorkflowEngine


@pytest.fixture
def engine() -> ProWorkflowEngine:
    orch = MagicMock()
    orch.run.return_value = {"output": "mock output"}
    return ProWorkflowEngine(orch=orch, memory=MagicMock())


@pytest.mark.parametrize(
    "mention,canonical",
    [
        ("素材", "material"),
        ("排版", "layout"),
        ("风格", "genre"),
        ("material", "material"),
        ("layout", "layout"),
        ("genre", "genre"),
    ],
)
def test_call_skill_direct_maps_display_name(engine: ProWorkflowEngine, mention: str, canonical: str) -> None:
    """中文 mention 应映射为 Skill 注册名后再调用 Orchestrator。"""
    result = engine._call_skill_direct(mention, {"slots": {}, "outputs": {}}, "user1")

    assert result["skill_name"] == canonical
    prompt = engine.orch.run.call_args[0][0]
    assert f"使用 {canonical} 技能。" in prompt


def test_call_skill_direct_keeps_display_name_in_reply(engine: ProWorkflowEngine) -> None:
    """回复消息中应保留用户可见的中文名称。"""
    result = engine._call_skill_direct("素材", {"slots": {}, "outputs": {}}, "user1")

    assert "素材" in result["reply"]
    assert result["skill_name"] == "material"
