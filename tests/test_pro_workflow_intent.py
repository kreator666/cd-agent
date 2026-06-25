"""喜剧龙虾意图分类测试 —— 防止核心维度被跳过，以及总编阶段行为。"""

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


def test_allows_jump_to_next_slot_when_current_slot_filled(skill: Skill) -> None:
    """当前槽位已填完时，允许顺序跳转到下一个维度。"""
    intent = skill._classify_intent("态度：我觉得这很荒谬", "话题专家", {"话题": "职场 PUA"})
    assert intent["type"] == "switch_role"
    assert intent.get("semantic_role") == "态度专家"
    assert intent.get("slot_name") == "态度"


def test_blocks_jump_when_current_slot_unfilled(skill: Skill) -> None:
    """当前槽位还没填完时，禁止被情绪等关键词误跳到后面维度。"""
    intent = skill._classify_intent("节奏先紧张后爆笑", "态度专家", {"话题": "职场 PUA"})
    assert intent["type"] == "chat"
    assert "semantic_role" not in intent


def test_blocks_skip_over_unfilled_slot(skill: Skill) -> None:
    """当前槽位已填完，但不允许跳过下一个未填充槽位。"""
    slots = {"话题": "职场 PUA", "态度": "愤怒"}
    # 此时应下一个未填充槽位是 偏见；语义推断到 情绪 应被忽略
    intent = skill._classify_intent("情绪：先紧张后爆笑", "态度专家", slots)
    assert intent["type"] == "chat"
    assert intent.get("semantic_role") != "情绪专家"


def test_allows_explicit_mention_to_jump(skill: Skill) -> None:
    """显式 @ 不受顺序限制，允许用户主动跳转到任意维度。"""
    intent = skill._classify_intent("@情绪专家 先紧张后爆笑", "话题专家", {"话题": "职场 PUA"})
    assert intent["type"] == "fill_slot"
    assert intent.get("mentioned_role") == "情绪专家"
    assert intent.get("slot_name") == "情绪"


def test_chief_editor_review_prompts_on_first_entry(
    skill: Skill, full_slots: dict[str, str]
) -> None:
    """总编审阅阶段首次进入应先给提示，不生成。"""
    workflow_step = {"action": "review", "state_id": "chief_editor_review", "role": "总编"}
    result = skill._run(
        workflow_step=workflow_step,
        slots=full_slots,
        outputs={},
        user_input="从紧张到爆笑",
        user_id="user1",
    )
    data = json.loads(result)
    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert data["outputs_update"]["chief_editor_prompted"] is True
    assert not data["artifacts"]


def test_chief_editor_review_any_input_generates_section(
    skill: Skill, full_slots: dict[str, str]
) -> None:
    """总编审阅阶段用户给出想法后生成第 1 段，不强套一次性/按小节模式。"""
    workflow_step = {"action": "review", "state_id": "chief_editor_review", "role": "总编"}
    with patch.object(skill, "_generate_script_content", return_value="mock section content"):
        result = skill._run(
            workflow_step=workflow_step,
            slots=full_slots,
            outputs={"chief_editor_prompted": True},
            user_input="先写个开场",
            user_id="user1",
        )
    data = json.loads(result)
    assert data["state_update"]["current_state"] == "chief_editor_review"
    assert "section_index" in data["outputs_update"]
    assert "section_outline" not in data["outputs_update"]
    assert any(a["type"] == "script" for a in data["artifacts"])


def test_chief_editor_review_finish_goes_done(
    skill: Skill, full_slots: dict[str, str]
) -> None:
    """总编审阅阶段用户说「完成」才进入 done。"""
    workflow_step = {"action": "review", "state_id": "chief_editor_review", "role": "总编"}
    outputs = {
        "chief_editor_prompted": True,
        "generated_sections": ["## 第 1 段\n\nmock section content"],
    }
    result = skill._run(
        workflow_step=workflow_step,
        slots=full_slots,
        outputs=outputs,
        user_input="完成",
        user_id="user1",
    )
    data = json.loads(result)
    assert data["state_update"]["current_state"] == "done"
    assert "mock section content" in data["outputs_update"].get("final_script", "")
