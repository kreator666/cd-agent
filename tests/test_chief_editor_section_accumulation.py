"""总编节点重构后行为测试。

新行为：
- 四槽位集齐后进入 chief_editor_review，总编先给用户提示，不替用户决定。
- 用户每次输入一个想法，总编生成一段；生成后回到 chief_editor_review。
- 默认追加新段落，不改动已有段落。
- 只有明确说「重写第 N 段」才修改已有段落。
- 只有明确说「完成/结束/done/finish/定稿/就这些/就到这/到此为止」才进入 done。
- 上下文保持一定逻辑性：生成时传入全部前文。
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
def review_workflow_step() -> dict[str, str]:
    return {"action": "review", "state_id": "chief_editor_review", "role": "总编"}


@pytest.fixture
def generate_workflow_step() -> dict[str, str]:
    return {"action": "generate", "state_id": "chief_editor_writing", "role": "总编", "mode": "section"}


def _parse_result(result: str) -> dict:
    return json.loads(result)


def test_first_entry_to_review_prompts_user(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """首次进入 chief_editor_review 应给用户提示，不直接生成。"""
    result = skill._run(
        workflow_step=review_workflow_step,
        slots=full_slots,
        outputs={},
        user_input="从紧张到爆笑",
        user_id="user1",
    )
    data = _parse_result(result)

    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert data["outputs_update"]["chief_editor_prompted"] is True
    assert "四维度" in data["reply"]
    assert "想写什么" in data["reply"] or "想法" in data["reply"]
    assert not data["artifacts"]


def test_review_after_prompt_generates_first_section(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """用户给出想法后，总编生成第 1 段。"""
    outputs = {"chief_editor_prompted": True}
    with patch.object(skill, "_call_llm", return_value="第一段正文") as mock_llm:
        result = skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="先写被领导盯着的开场",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert out["section_index"] == 0
    assert len(out["generated_sections"]) == 1
    assert out["generated_sections"][0] == "## 第 1 段\n\n第一段正文"
    assert data["artifacts"][0]["op"] == "create"
    assert "先写被领导盯着的开场" in mock_llm.call_args[0][1]


def test_review_appends_new_section_for_each_idea(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """每次给出新想法都追加一段，不改动已有段落。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\n第一段正文"],
    }
    with patch.object(skill, "_call_llm", return_value="第二段正文"):
        result = skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="再写写同事关系",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2
    assert out["generated_sections"][0] == "## 第 1 段\n\n第一段正文"
    assert out["generated_sections"][1] == "## 第 2 段\n\n第二段正文"
    assert data["artifacts"][0]["op"] == "append"


def test_review_explicit_rewrite_modifies_section(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """明确说「重写第 2 段」时才修改第 2 段。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\n第一段正文", "## 第 2 段\n\nold section 2"],
    }
    with patch.object(skill, "_call_llm", return_value="第二段正文 v2"):
        result = skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="重写第 2 段，太平了加点攻击性",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2
    assert out["generated_sections"][1] == "## 第 2 段\n\n第二段正文 v2"
    assert data["artifacts"][0]["op"] == "update"


def test_vague_modify_input_is_treated_as_new_section(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """没有明确段号的「太平了」应被当作新想法追加，而不是修改当前段。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\n第一段正文"],
    }
    with patch.object(skill, "_call_llm", return_value="第二段正文"):
        result = skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="太平了，再加点攻击性",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2
    assert out["generated_sections"][1] == "## 第 2 段\n\n第二段正文"


def test_finish_command_goes_done(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """用户明确说「完成」时进入 done，合并所有段落。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\n第一段正文", "## 第 2 段\n\n第二段正文"],
    }
    result = skill._run(
        workflow_step=review_workflow_step,
        slots=full_slots,
        outputs=outputs,
        user_input="完成",
        user_id="user1",
    )
    data = _parse_result(result)

    assert data["state_update"]["current_state"] == "done"
    assert "第一段正文" in data["outputs_update"]["final_script"]
    assert "第二段正文" in data["outputs_update"]["final_script"]


def test_hao_le_does_not_finish(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """「好了」不应被误判为结束，应作为写作想法追加。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\n第一段正文"],
    }
    with patch.object(skill, "_call_llm", return_value="第二段正文"):
        result = skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="好了，再写写同事关系",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2


def test_generate_action_directly_generates_section(
    skill: Skill, full_slots: dict[str, str], generate_workflow_step: dict[str, str]
) -> None:
    """action=generate 时直接生成一段（兼容工作流引擎调用）。"""
    with patch.object(skill, "_call_llm", return_value="第一段正文"):
        result = skill._run(
            workflow_step=generate_workflow_step,
            slots=full_slots,
            outputs={},
            user_input="按小节生成",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert len(out["generated_sections"]) == 1
    assert out["generated_sections"][0] == "## 第 1 段\n\n第一段正文"


def test_full_previous_sections_passed_to_llm(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """生成第 3 段时，应把第 1、2 段全部前文传入 LLM。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\n第一段正文", "## 第 2 段\n\n第二段正文"],
    }
    with patch.object(skill, "_call_llm", return_value="第三段正文") as mock_llm:
        skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续写收尾",
            user_id="user1",
        )
    system_prompt = mock_llm.call_args[0][0]
    assert "第一段正文" in system_prompt
    assert "第二段正文" in system_prompt
