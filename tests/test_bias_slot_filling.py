"""偏见槽位收集测试。

验证在偏见专家阶段，用户给出偏见内容后：
- 偏见槽位能被正确填充；
- 状态能推进到情绪阶段；
- LLM 未显式返回 slot_value 时，兜底填充能生效。
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from skills.get_daren.skill import Skill


@pytest.fixture
def skill() -> Skill:
    return Skill()


def _parse_result(result: str) -> dict:
    return json.loads(result)


def test_bias_slot_filled_when_llm_returns_slot_value(skill: Skill) -> None:
    """偏见专家 LLM 正确返回 slot_name/slot_value 时，偏见槽位应被填充并推进。"""
    workflow_step = {"action": "guide", "state_id": "bias_filling", "role": "偏见专家"}
    llm_output = json.dumps({
        "reply": "这个偏见很犀利，我们来确认一下情绪节奏。",
        "role": "偏见专家",
        "next_role": "情绪专家",
        "advance": True,
        "slot_name": "偏见",
        "slot_value": "领导永远是对的",
    }, ensure_ascii=False)

    with patch.object(skill, "_call_llm", return_value=llm_output):
        result = skill._run(
            workflow_step=workflow_step,
            slots={"话题": "职场PUA", "态度": "愤怒"},
            outputs={},
            user_input="领导永远是对的",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["slots_update"].get("偏见") == "领导永远是对的"
    assert data["state_update"]["current_state"] == "emotion_filling"


def test_bias_slot_filled_via_fallback_when_llm_does_not_return_slot(skill: Skill) -> None:
    """LLM 未返回 slot_name/slot_value 时，兜底逻辑应把用户输入填入偏见槽位。"""
    workflow_step = {"action": "guide", "state_id": "bias_filling", "role": "偏见专家"}
    llm_output = json.dumps({
        "reply": "好的，这个视角很有意思。",
        "role": "偏见专家",
        "next_role": "情绪专家",
        "advance": False,
    }, ensure_ascii=False)

    with patch.object(skill, "_call_llm", return_value=llm_output):
        result = skill._run(
            workflow_step=workflow_step,
            slots={"话题": "职场PUA", "态度": "愤怒"},
            outputs={},
            user_input="领导永远是对的",
            user_id="user1",
        )
    data = _parse_result(result)
    assert data["slots_update"].get("偏见") == "领导永远是对的"


def test_bias_slot_not_overwritten_when_already_filled(skill: Skill) -> None:
    """偏见槽位已有值时，用户再输入不应被兜底覆盖。"""
    workflow_step = {"action": "guide", "state_id": "bias_filling", "role": "偏见专家"}
    llm_output = json.dumps({
        "reply": "偏见已经确认过了。",
        "role": "偏见专家",
        "next_role": "情绪专家",
        "advance": False,
    }, ensure_ascii=False)

    with patch.object(skill, "_call_llm", return_value=llm_output):
        result = skill._run(
            workflow_step=workflow_step,
            slots={"话题": "职场PUA", "态度": "愤怒", "偏见": "领导永远是对的"},
            outputs={},
            user_input="换个角度：加班才是努力",
            user_id="user1",
        )
    data = _parse_result(result)
    assert "偏见" not in data["slots_update"] or data["slots_update"]["偏见"] == "领导永远是对的"


def test_bias_slot_filled_via_mention(skill: Skill) -> None:
    """用户显式 @偏见专家 时，应直接填充偏见槽位。"""
    workflow_step = {"action": "guide", "state_id": "guiding", "role": "主持人"}
    result = skill._run(
        workflow_step=workflow_step,
        slots={"话题": "职场PUA", "态度": "愤怒"},
        outputs={},
        user_input="@偏见专家 领导永远是对的",
        user_id="user1",
    )
    data = _parse_result(result)
    assert data["slots_update"].get("偏见") == "领导永远是对的"
    assert data["state_update"]["current_state"] == "emotion_filling"


def test_attitude_to_bias_transition_by_semantic_jump(skill: Skill) -> None:
    """当前在态度专家阶段，用户输入偏见内容时，应跳转到偏见专家并填充偏见槽位。"""
    workflow_step = {"action": "guide", "state_id": "attitude_filling", "role": "态度专家"}
    llm_output = json.dumps({
        "reply": "我来提炼这个偏见。",
        "role": "态度专家",
        "next_role": "偏见专家",
        "advance": False,
    }, ensure_ascii=False)

    with patch.object(skill, "_call_llm", return_value=llm_output):
        result = skill._run(
            workflow_step=workflow_step,
            slots={"话题": "职场PUA", "态度": "愤怒"},
            outputs={},
            user_input="偏见：领导永远是对的",
            user_id="user1",
        )
    data = _parse_result(result)
    # 用户明确说了“偏见：xxx”，_infer_role_from_text 应识别并跳转
    assert data["slots_update"].get("偏见") == "领导永远是对的"
    assert data["state_update"]["current_state"] == "emotion_filling"
