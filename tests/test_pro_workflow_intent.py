"""喜剧龙虾意图分类测试 —— 防止核心维度被跳过。"""

from __future__ import annotations

import pytest

from skills.get_daren.skill import Skill


@pytest.fixture
def skill() -> Skill:
    return Skill()


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
