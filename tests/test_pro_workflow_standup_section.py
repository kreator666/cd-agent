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
