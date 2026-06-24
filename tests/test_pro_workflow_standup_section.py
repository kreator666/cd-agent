"""分段脱口秀生成（多轮对话续写）测试。

按小节生成不是按固定大纲分小节输出，而是与 LLM 进行多轮对话：
- 每轮根据四维度 + 用户最新输入 + 已生成前文，生成一个子话题段落；
- 用户可以一直续写，直到明确说「完成」。
"""

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


def _parse_result(result: str) -> dict:
    return json.loads(result)


def test_first_section_generates_without_outline(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """首次进入分段生成应直接写第 1 段，不预生成固定大纲。"""
    with patch.object(skill, "_call_llm", return_value="mock section 1"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs={},
            user_input="按小节生成",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["state_update"]["current_state"] == "generating_section"
    assert data["outputs_update"]["section_status"] == "awaiting_confirm"
    assert data["outputs_update"]["section_index"] == 0
    assert len(data["outputs_update"]["generated_sections"]) == 1
    assert "section_outline" not in data["outputs_update"]
    assert any(a["title"] == "脱口秀分段稿件" for a in data["artifacts"])
    assert "继续生成下一段" in str(data.get("next_actions", []))


def test_continue_generates_next_section(skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]) -> None:
    """回复「继续」应生成下一段，索引递增，不覆盖前文。"""
    outputs = {
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\nmock section 1"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="mock section 2"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["outputs_update"]["section_index"] == 1
    assert len(data["outputs_update"]["generated_sections"]) == 2
    assert data["outputs_update"]["section_status"] == "awaiting_confirm"
    assert data["artifacts"][0]["op"] == "append"


def test_retry_regenerates_current_section(skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]) -> None:
    """显式回复「修改」应重新生成当前段，索引不变，并传入用户反馈。"""
    outputs = {
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\nmock section 1", "## 第 2 段\n\nold section 2"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="mock section 2 v2") as mock_gen:
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="修改：太平了，加点攻击性",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["outputs_update"]["section_index"] == 1
    assert len(data["outputs_update"]["generated_sections"]) == 2
    assert data["artifacts"][0]["op"] == "update"
    # update 时应返回完整合并后的稿件，确保前端能整体替换
    assert "## 第 1 段" in data["artifacts"][0]["content"]
    assert "mock section 2 v2" in data["artifacts"][0]["content"]
    # feedback 应被传入 _call_llm
    user_prompt = mock_gen.call_args[0][1]
    assert "太平了，加点攻击性" in user_prompt


def test_default_continue_generates_next_section(skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]) -> None:
    """用户没有明确说完成/修改时，默认继续生成下一段，符合主编「一直写」的预期。"""
    outputs = {
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\nmock section 1"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="mock section 2"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="ok",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["outputs_update"]["section_index"] == 1
    assert len(data["outputs_update"]["generated_sections"]) == 2
    assert data["outputs_update"]["section_status"] == "awaiting_confirm"


def test_free_text_generates_next_subtopic(skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]) -> None:
    """自由文本应作为下一段的子话题方向，而不是修改当前段。"""
    outputs = {
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\nmock section 1"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="mock section 2") as mock_gen:
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="再写写同事关系",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["outputs_update"]["section_index"] == 1
    assert len(data["outputs_update"]["generated_sections"]) == 2
    # 子话题方向应传入 LLM
    user_prompt = mock_gen.call_args[0][1]
    assert "同事关系" in user_prompt


def test_finish_combines_sections_and_goes_done(skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]) -> None:
    """回复「完成」应合并所有段落并进入 done 状态。"""
    outputs = {
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\nmock section 1", "## 第 2 段\n\nmock section 2"],
        "section_status": "awaiting_confirm",
    }
    result = skill._run(
        workflow_step=section_workflow_step,
        slots=full_slots,
        outputs=outputs,
        user_input="完成",
        user_id="user1",
    )
    data = _parse_result(result)
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
    with patch.object(skill, "_call_llm", return_value="mock section 1") as mock_gen:
        result = skill._run(
            workflow_step=workflow_step,
            slots=full_slots,
            outputs={},
            user_input=user_input,
            user_id="user1",
        )
    data = _parse_result(result)
    assert "四个维度已集齐" not in data["reply"]
    assert data["state_update"]["current_state"] == "generating_section"
    assert "注重吐槽的幽默和加梗" in data["outputs_update"]["section_requirements"]
    # 第一段生成时就要把全局要求传进去
    system_prompt = mock_gen.call_args[0][0]
    assert "注重吐槽" in system_prompt


def test_feedback_defaults_to_retry_not_continue(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """用户给出风格/修改意见（如「太平了」）时，应重写当前段而不是继续下一段。"""
    outputs = {
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\nmock section 1"],
        "script_main": "## 第 1 段\n\nmock section 1",
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="mock section 1 v2") as mock_gen:
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="太平了，加点攻击性",
            user_id="user1",
        )
    data = _parse_result(result)
    # 索引不变，当前段被重写
    assert data["outputs_update"]["section_index"] == 0
    assert len(data["outputs_update"]["generated_sections"]) == 1
    assert data["artifacts"][0]["op"] == "update"
    user_prompt = mock_gen.call_args[0][1]
    assert "太平了，加点攻击性" in user_prompt


def test_continue_is_unlimited_no_outline_boundary(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """没有固定大纲长度限制，已生成 3 段后仍可继续生成第 4 段。"""
    outputs = {
        "section_index": 2,
        "generated_sections": [
            "## 第 1 段\n\nmock section 1",
            "## 第 2 段\n\nmock section 2",
            "## 第 3 段\n\nmock section 3",
        ],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="mock section 4"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["outputs_update"]["section_index"] == 3
    assert len(data["outputs_update"]["generated_sections"]) == 4
    assert data["outputs_update"]["section_status"] == "awaiting_confirm"


def test_natural_language_prev_section(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """「上一段太平了」应回到上一段重写，而不是覆盖当前段或结束。"""
    outputs = {
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\nmock section 1", "## 第 2 段\n\nmock section 2"],
        "script_main": "## 第 1 段\n\nmock section 1\n\n## 第 2 段\n\nmock section 2",
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="mock section 1 v2") as mock_gen:
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="上一段太平了",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["outputs_update"]["section_index"] == 0
    user_prompt = mock_gen.call_args[0][1]
    assert "太平了" in user_prompt


def test_natural_language_modify_current_section(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """「不要说套话」应重写当前段，而不是继续下一段。"""
    outputs = {
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\nmock section 1"],
        "script_main": "## 第 1 段\n\nmock section 1",
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="mock section 1 v2") as mock_gen:
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="不要说套话",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["outputs_update"]["section_index"] == 0
    assert len(data["outputs_update"]["generated_sections"]) == 1
    user_prompt = mock_gen.call_args[0][1]
    assert "套话" in user_prompt
