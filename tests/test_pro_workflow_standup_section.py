"""总编节点重构后分段生成测试。

新行为：
- 总编先收集用户想法，再按想法生成单段。
- 默认追加，只有明确「重写第 N 段」才修改。
- 不自动结束，不预生成大纲，不强套结构。
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
    return {"action": "generate", "state_id": "chief_editor_writing", "mode": "section", "role": "总编"}


def _parse_result(result: str) -> dict:
    return json.loads(result)


def test_review_first_entry_prompts_user(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """首次进入总编审阅阶段应先给提示。"""
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
    assert not data["artifacts"]


def test_review_generates_first_section_after_user_idea(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """用户给出想法后生成第 1 段，不预生成大纲。"""
    outputs = {"chief_editor_prompted": True}
    with patch.object(skill, "_call_llm", return_value="mock section 1"):
        result = skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="按小节生成，注意黑色幽默",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert len(data["outputs_update"]["generated_sections"]) == 1
    assert data["artifacts"][0]["op"] == "create"


def test_generate_action_directly_generates_first_section(
    skill: Skill, full_slots: dict[str, str], generate_workflow_step: dict[str, str]
) -> None:
    """action=generate 直接生成第 1 段。"""
    with patch.object(skill, "_call_llm", return_value="mock section 1"):
        result = skill._run(
            workflow_step=generate_workflow_step,
            slots=full_slots,
            outputs={},
            user_input="按小节生成",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert len(data["outputs_update"]["generated_sections"]) == 1


def test_review_appends_by_default(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """默认追加新段，不改动已有段落。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\nmock section 1"],
    }
    with patch.object(skill, "_call_llm", return_value="mock section 2"):
        result = skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]
    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2
    assert out["generated_sections"][0] == "## 第 1 段\n\nmock section 1"
    assert data["artifacts"][0]["op"] == "append"


def test_review_explicit_rewrite_updates_section(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """明确「重写第 1 段」才更新已有段落。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\nmock section 1"],
    }
    with patch.object(skill, "_call_llm", return_value="mock section 1 v2"):
        result = skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="重写第 1 段，太平了",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]
    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert out["section_index"] == 0
    assert len(out["generated_sections"]) == 1
    assert out["generated_sections"][0] == "## 第 1 段\n\nmock section 1 v2"
    assert data["artifacts"][0]["op"] == "update"


def test_finish_combines_sections_and_goes_done(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """明确「完成」进入 done。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\nmock section 1", "## 第 2 段\n\nmock section 2"],
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
    assert "mock section 1" in data["outputs_update"]["final_script"]
    assert "mock section 2" in data["outputs_update"]["final_script"]


def test_free_text_generates_next_subtopic(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """自由文本作为新子话题追加。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\nmock section 1"],
    }
    with patch.object(skill, "_call_llm", return_value="mock section 2") as mock_llm:
        result = skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="再写写同事关系",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert data["outputs_update"]["section_index"] == 1
    assert "同事关系" in mock_llm.call_args[0][1]


def test_unlimited_append_no_outline_boundary(
    skill: Skill, full_slots: dict[str, str], review_workflow_step: dict[str, str]
) -> None:
    """没有大纲长度限制，可以一直追加。"""
    outputs = {
        "chief_editor_prompted": True,
        "section_index": 2,
        "generated_sections": [
            "## 第 1 段\n\nmock section 1",
            "## 第 2 段\n\nmock section 2",
            "## 第 3 段\n\nmock section 3",
        ],
    }
    with patch.object(skill, "_call_llm", return_value="mock section 4"):
        result = skill._run(
            workflow_step=review_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]
    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert out["section_index"] == 3
    assert len(out["generated_sections"]) == 4
    assert data["artifacts"][0]["op"] == "append"
