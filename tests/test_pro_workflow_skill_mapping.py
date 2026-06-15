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


def test_process_returns_skill_output_content(engine: ProWorkflowEngine) -> None:
    """@mention 调用外部 Skill 时，返回的 content 应为 Skill 实际输出而非调用提示。"""
    engine.orch.run.return_value = {
        "output": "📚 参考素材：\n1. **示例标题**\n   示例摘要\n   来源：http://example.com",
        "messages": [],
    }

    result = engine.process(
        session_id=None,
        user_id="user1",
        message="@素材 职场 PUA",
        outline="职场 PUA",
        persona_id=None,
        model=None,
    )

    assert result["type"] == "skill_output"
    assert result["skill_name"] == "素材"
    assert "参考素材" in result["content"]
    assert "正在调用" not in result["content"]
    steps = result.get("steps", [])
    assert any(
        step.get("type") == "skill_output" and "参考素材" in (step.get("content") or "")
        for step in steps
    )


def test_material_uses_user_query_not_outline(engine: ProWorkflowEngine) -> None:
    """@素材 时，应使用用户消息中的查询词，而非工作流 outline。"""
    engine.process(
        session_id=None,
        user_id="user1",
        message="@素材 带孩子做作业",
        outline="伊朗核问题",
        persona_id=None,
        model=None,
    )

    prompt = engine.orch.run.call_args[0][0]
    assert "搜索词：带孩子做作业" in prompt
    assert "伊朗" not in prompt
    assert "职场" not in prompt
