"""ProWorkflowEngine 中文 Skill mention 映射测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from comedy_agent.api.routers.pro_workflow import ProWorkflowEngine


@pytest.fixture
def engine() -> ProWorkflowEngine:
    orch = MagicMock()
    orch.run.return_value = {"output": "mock output"}

    # layout skill 现在被直接调用，不经过 orch.run
    layout_skill = MagicMock()
    layout_skill.invoke.return_value = "layout mock output"
    orch._find_skill.return_value = layout_skill

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
    """中文 mention 应映射为 Skill 注册名后再调用。"""
    # 排版 skill 需要实际内容或用户查询才会调用
    if canonical == "layout":
        wf_state = {"slots": {"outline": "家庭教育"}, "outputs": {}}
        message = f"@{mention} 用小红书风格排版"
    else:
        wf_state = {"slots": {}, "outputs": {}}
        message = ""

    result = engine._call_skill_direct(mention, wf_state, "user1", message=message)

    assert result["skill_name"] == canonical
    if canonical == "layout":
        engine.orch._find_skill.assert_called_with("layout")
        engine.orch._find_skill.return_value.invoke.assert_called()
    else:
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


def test_layout_consultation_returns_help_without_llm(engine: ProWorkflowEngine) -> None:
    """@排版 咨询平台时，应直接返回帮助信息，不应调用 LLM。"""
    result = engine.process(
        session_id=None,
        user_id="user1",
        message="@排版 将结果排版，可以排成什么样的？",
        outline="家庭教育",
        persona_id=None,
        model=None,
    )

    assert result["type"] == "skill_output"
    assert result["skill_name"] == "排版"
    assert "微信公众号" in result["content"]
    assert "小红书" in result["content"]
    assert "知乎" in result["content"]
    assert "B站专栏" in result["content"]
    # 未触发 Orchestrator 的 LLM 调用
    engine.orch.run.assert_not_called()


def test_layout_final_script_uses_final_output(engine: ProWorkflowEngine) -> None:
    """@排版 要求排版最终结果时，应使用 outputs.final_script 作为正文。"""
    final_script = "Z世代把生活当成代码来调试。"
    wf_state = {
        "slots": {"outline": "Z世代生活即代码"},
        "outputs": {"final_script": final_script},
    }
    engine._call_skill_direct(
        "排版",
        wf_state,
        "user1",
        message="@排版 将这篇文章最终结果 按 微信公众号 排版",
    )

    # layout skill 被直接调用，且传入了 final_script 和平台
    args = engine.orch._find_skill.return_value.invoke.call_args[0][0]
    assert final_script in args["text"]
    assert args["platform"] == "wechat"


def test_layout_final_script_missing_prompts_generate(engine: ProWorkflowEngine) -> None:
    """@排版 要求排版最终结果但尚未生成时，应提示用户先生成。"""
    result = engine.process(
        session_id=None,
        user_id="user1",
        message="@排版 将这篇文章最终结果 按 微信公众号 排版",
        outline="Z世代生活即代码",
        persona_id=None,
        model=None,
    )

    assert result["type"] == "skill_output"
    assert "还没有生成最终剧本" in result["content"] or "还没有生成最终剧本" in result.get("steps", [{}])[0].get("content", "")
    engine.orch._find_skill.return_value.invoke.assert_not_called()


def test_layout_with_content_and_platform_uses_skill(engine: ProWorkflowEngine) -> None:
    """@排版 有正文和平台要求时，应直接调用 layout skill 并传入正确参数。"""
    engine.process(
        session_id=None,
        user_id="user1",
        message="@排版 用小红书风格排版",
        outline="家庭教育",
        persona_id=None,
        model=None,
    )

    args = engine.orch._find_skill.return_value.invoke.call_args[0][0]
    assert "家庭教育" in args["text"]
    assert args["platform"] == "xiaohongshu"
