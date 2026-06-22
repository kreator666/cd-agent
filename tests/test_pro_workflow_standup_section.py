"""分段脱口秀生成确认循环测试。"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from skills.get_daren.skill import Skill


@pytest.fixture
def skill() -> Skill:
    return Skill()


@pytest.fixture
def full_slots() -> dict[str, str]:
    return {
        "话题": "职场 PUA",
        "态度": "愤怒",
        "偏见": "领导永远是对的",
        "情绪": "从紧张到爆笑",
    }


@pytest.fixture
def section_workflow_step() -> dict[str, str]:
    return {"action": "generate", "state_id": "generating_section", "mode": "section", "role": "总编"}


def _parse_result(skill: Skill, result: str) -> dict:
    return json.loads(result)


def test_first_section_generates_outline_and_waits_for_confirm(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """首次进入分段生成应创建大纲、生成第 1 段并进入等待确认状态。"""
    with patch.object(skill, "_generate_section_outline", return_value=["开场铺垫", "观察升级", "收尾观点"]), \
         patch.object(skill, "_generate_script_content", return_value="mock section 1"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs={},
            user_input="按小节生成",
            user_id="user1",
        )
    data = _parse_result(skill, result)
    assert data["state_update"]["current_state"] == "generating_section"
    assert data["outputs_update"]["section_status"] == "awaiting_confirm"
    assert data["outputs_update"]["section_index"] == 0
    assert len(data["outputs_update"]["generated_sections"]) == 1
    assert any(a["title"] == "脱口秀分段稿件" for a in data["artifacts"])
    assert "继续生成下一段" in str(data.get("next_actions", []))


def test_continue_generates_next_section(skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]) -> None:
    """回复「继续」应生成下一段，索引递增。"""
    outputs = {
        "section_outline": ["开场铺垫", "观察升级", "收尾观点"],
        "section_index": 0,
        "generated_sections": ["## 开场铺垫\n\nmock section 1"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_generate_script_content", return_value="mock section 2"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续",
            user_id="user1",
        )
    data = _parse_result(skill, result)
    assert data["outputs_update"]["section_index"] == 1
    assert len(data["outputs_update"]["generated_sections"]) == 2
    assert data["outputs_update"]["section_status"] == "awaiting_confirm"
    assert data["artifacts"][0]["op"] == "append"


def test_retry_regenerates_current_section(skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]) -> None:
    """显式回复「修改」应重新生成当前段，索引不变，并传入用户反馈。"""
    outputs = {
        "section_outline": ["开场铺垫", "观察升级", "收尾观点"],
        "section_index": 1,
        "generated_sections": ["## 开场铺垫\n\nmock section 1", "## 观察升级\n\nold section 2"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_generate_script_content", return_value="mock section 2 v2") as mock_gen:
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="修改：太平了，加点攻击性",
            user_id="user1",
        )
    data = _parse_result(skill, result)
    assert data["outputs_update"]["section_index"] == 1
    assert len(data["outputs_update"]["generated_sections"]) == 2
    assert data["artifacts"][0]["op"] == "update"
    # update 时应返回完整合并后的稿件，确保前端能整体替换
    assert "## 开场铺垫" in data["artifacts"][0]["content"]
    assert "mock section 2 v2" in data["artifacts"][0]["content"]
    # feedback 应被传入 _generate_script_content
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs.get("feedback") == "修改：太平了，加点攻击性"


def test_default_continue_generates_next_section(skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]) -> None:
    """用户没有明确说完成/修改时，默认继续生成下一段，符合主编「一直写」的预期。"""
    outputs = {
        "section_outline": ["开场铺垫", "观察升级", "收尾观点"],
        "section_index": 0,
        "generated_sections": ["## 开场铺垫\n\nmock section 1"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_generate_script_content", return_value="mock section 2"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="ok",
            user_id="user1",
        )
    data = _parse_result(skill, result)
    assert data["outputs_update"]["section_index"] == 1
    assert len(data["outputs_update"]["generated_sections"]) == 2
    assert data["outputs_update"]["section_status"] == "awaiting_confirm"


def test_continue_without_section_status_still_advances(skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]) -> None:
    """即使 section_status 未落库，只要有已生成段落，继续就应生成下一段而不是覆盖。"""
    outputs = {
        "section_outline": ["开场铺垫", "观察升级", "收尾观点"],
        "section_index": 0,
        "generated_sections": ["## 开场铺垫\n\nmock section 1"],
        # 故意不设置 section_status，模拟落库异常
    }
    with patch.object(skill, "_generate_script_content", return_value="mock section 2"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续",
            user_id="user1",
        )
    data = _parse_result(skill, result)
    assert data["outputs_update"]["section_index"] == 1
    assert len(data["outputs_update"]["generated_sections"]) == 2
    assert data["artifacts"][0]["op"] == "append"
    assert "mock section 1" in data["outputs_update"]["final_script"]
    assert "mock section 2" in data["outputs_update"]["final_script"]


def test_finish_combines_sections_and_goes_done(skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]) -> None:
    """回复「完成」应合并所有段落并进入 done 状态。"""
    outputs = {
        "section_outline": ["开场铺垫", "观察升级", "收尾观点"],
        "section_index": 1,
        "generated_sections": ["## 开场铺垫\n\nmock section 1", "## 观察升级\n\nmock section 2"],
        "section_status": "awaiting_confirm",
    }
    result = skill._run(
        workflow_step=section_workflow_step,
        slots=full_slots,
        outputs=outputs,
        user_input="完成",
        user_id="user1",
    )
    data = _parse_result(skill, result)
    assert data["state_update"]["current_state"] == "done"
    assert "mock section 1" in data["outputs_update"]["final_script"]
    assert "mock section 2" in data["outputs_update"]["final_script"]
    assert data["outputs_update"]["section_status"] == "finished"


def test_chief_editor_mode_with_requirements_skips_ask(
    skill: Skill, full_slots: dict[str, str]
) -> None:
    """总编阶段用户直接说「分小节生成 + 要求」时，不应再询问生成方式，且要求要保留。"""
    workflow_step = {"action": "guide", "state_id": "chief_editor_review", "role": "总编"}
    user_input = "分小节生成。注重吐槽的幽默和加梗，不要说套话"
    with patch.object(skill, "_generate_section_outline", return_value=["开场铺垫", "观察升级", "收尾观点"]), \
         patch.object(skill, "_generate_script_content", return_value="mock section 1") as mock_gen:
        result = skill._run(
            workflow_step=workflow_step,
            slots=full_slots,
            outputs={},
            user_input=user_input,
            user_id="user1",
        )
    data = _parse_result(skill, result)
    assert "四个维度已集齐" not in data["reply"]
    assert data["state_update"]["current_state"] == "generating_section"
    assert "注重吐槽的幽默和加梗" in data["outputs_update"]["section_requirements"]
    # 第一段生成时就要把全局要求传进去
    assert "注重吐槽" in mock_gen.call_args.kwargs.get("feedback", "")


def test_feedback_defaults_to_retry_not_continue(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """用户给出风格/修改意见（如「太平了」）时，应重写当前段而不是继续下一段。"""
    outputs = {
        "section_outline": ["开场铺垫", "观察升级", "收尾观点"],
        "section_index": 0,
        "generated_sections": ["## 开场铺垫\n\nmock section 1"],
        "script_main": "## 开场铺垫\n\nmock section 1",
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_generate_script_content", return_value="mock section 1 v2") as mock_gen:
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="太平了，加点攻击性",
            user_id="user1",
        )
    data = _parse_result(skill, result)
    # 索引不变，当前段被重写
    assert data["outputs_update"]["section_index"] == 0
    assert len(data["outputs_update"]["generated_sections"]) == 1
    assert data["artifacts"][0]["op"] == "update"
    assert "太平了，加点攻击性" in mock_gen.call_args.kwargs.get("feedback", "")


def test_continue_after_last_section_does_not_auto_finish(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """已经到最后一段时，用户没说「完成」就不应自动结束生成。"""
    outputs = {
        "section_outline": ["开场铺垫", "观察升级"],
        "section_index": 1,
        "generated_sections": ["## 开场铺垫\n\nmock section 1", "## 观察升级\n\nmock section 2"],
        "section_status": "awaiting_confirm",
    }
    result = skill._run(
        workflow_step=section_workflow_step,
        slots=full_slots,
        outputs=outputs,
        user_input="继续",
        user_id="user1",
    )
    data = _parse_result(skill, result)
    assert data["state_update"]["current_state"] != "done"
    assert data["outputs_update"]["section_status"] == "awaiting_confirm"
    assert "所有段落已生成完毕" in data["reply"] or "完成" in data["reply"]
