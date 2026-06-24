"""总编分段输出（多轮对话续写）累积性测试。

验证按小节生成模式下：
- 不预生成固定大纲；
- 每轮根据用户输入生成一个子话题段落；
- 用户可以无限续写，直到说「完成」；
- generated_sections / final_script 正确累积，不会被覆盖。
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


def test_first_section_starts_without_outline(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """首次进入分段生成应直接写第 1 段，不预生成固定大纲。"""
    with patch.object(skill, "_call_llm", return_value="第一段正文"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs={},
            user_input="按小节生成",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert data["state_update"]["current_state"] == "generating_section"
    assert out["section_status"] == "awaiting_confirm"
    assert out["section_index"] == 0
    assert len(out["generated_sections"]) == 1
    assert "section_outline" not in out
    assert out["generated_sections"][0] == "## 第 1 段\n\n第一段正文"
    assert data["artifacts"][0]["op"] == "create"


def test_continue_generates_next_subtopic(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """回复「继续」应生成下一段子话题，并追加到已有段落之后。"""
    outputs = {
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\n第一段正文"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="第二段正文"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2
    assert out["generated_sections"] == [
        "## 第 1 段\n\n第一段正文",
        "## 第 2 段\n\n第二段正文",
    ]
    assert data["artifacts"][0]["op"] == "append"
    assert data["artifacts"][0]["content"] == "## 第 2 段\n\n第二段正文"


def test_free_text_becomes_next_subtopic(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """用户输入具体方向（如“再写写同事关系”）应作为下一段子话题，而不是修改当前段。"""
    outputs = {
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\n第一段正文"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="同事关系段子") as mock_llm:
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="再写写同事关系",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2
    assert out["generated_sections"][1] == "## 第 2 段\n\n同事关系段子"
    assert data["artifacts"][0]["op"] == "append"
    # 子话题方向应传入 _call_llm 的 user_prompt
    assert "同事关系" in mock_llm.call_args[0][1]


def test_modify_regenerates_current_section(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """显式修改意见应重写当前段，而不是新增一段。"""
    outputs = {
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\n第一段正文", "## 第 2 段\n\nold section 2"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="第二段正文 v2") as mock_llm:
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="太平了，加点攻击性",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2
    assert out["generated_sections"][1] == "## 第 2 段\n\n第二段正文 v2"
    assert data["artifacts"][0]["op"] == "update"
    assert "太平了" in mock_llm.call_args[0][1]


def test_prev_regenerates_previous_section(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """「上一段太平了」应回到上一段重写，索引递减。"""
    outputs = {
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\n第一段正文", "## 第 2 段\n\n第二段正文"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="第一段正文 v2") as mock_llm:
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="上一段太平了",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert out["section_index"] == 0
    assert out["generated_sections"][0] == "## 第 1 段\n\n第一段正文 v2"
    assert len(out["generated_sections"]) == 2
    assert "太平了" in mock_llm.call_args[0][1]


def test_finish_combines_sections_and_goes_done(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """回复「完成」应合并所有段落并进入 done 状态。"""
    outputs = {
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\n第一段正文", "## 第 2 段\n\n第二段正文"],
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
    assert "第一段正文" in data["outputs_update"]["final_script"]
    assert "第二段正文" in data["outputs_update"]["final_script"]


def test_unlimited_continue_no_outline_limit(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """没有固定大纲长度限制，用户可以一直继续生成新段。"""
    outputs = {
        "section_index": 2,
        "generated_sections": [
            "## 第 1 段\n\n第一段正文",
            "## 第 2 段\n\n第二段正文",
            "## 第 3 段\n\n第三段正文",
        ],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="第四段正文"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert out["section_index"] == 3
    assert len(out["generated_sections"]) == 4
    assert out["generated_sections"][3] == "## 第 4 段\n\n第四段正文"
    assert data["artifacts"][0]["op"] == "append"


def test_sanitize_repeated_previous_section(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """LLM 重复输出前文时，后处理应截断到只保留当前段新内容。"""
    long_body = "第一段正文" * 17  # 确保 >=80 字符，触发长重复截断
    outputs = {
        "section_index": 0,
        "generated_sections": [f"## 第 1 段\n\n{long_body}"],
        "section_status": "awaiting_confirm",
    }

    misbehaving_content = f"{long_body}\n\n第二段正文"

    with patch.object(skill, "_call_llm", return_value=misbehaving_content):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2
    assert out["generated_sections"][1] == "## 第 2 段\n\n第二段正文"


def test_short_repeated_prefix_not_truncated(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """常见短开头相似时，不应被误当成前文重复而截断新段落。"""
    outputs = {
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\n我最近发现职场 PUA 真的无处不在。"],
        "section_status": "awaiting_confirm",
    }
    # 新段以相同短句开头，但后面是全新内容
    new_content = "我最近发现职场 PUA 真的无处不在。而且最可怕的是，有时候连你自己都没意识到被 PUA 了。"

    with patch.object(skill, "_call_llm", return_value=new_content):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="写写自我觉察",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2
    assert "自我觉察" not in out["generated_sections"][1]  # 用户输入不会出现在结果中
    assert "最可怕的是" in out["generated_sections"][1]
    assert "## 第 2 段" in out["generated_sections"][1]


def test_hao_le_does_not_finish(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """「好了」「好的」等日常用语不应被误判为结束生成。"""
    outputs = {
        "section_index": 0,
        "generated_sections": ["## 第 1 段\n\n第一段正文"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="第二段正文"):
        result = skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="好了，再写写同事关系",
            user_id="user1",
        )
    data = _parse_result(result)
    out = data["outputs_update"]

    assert data["state_update"]["current_state"] == "generating_section"
    assert out["section_index"] == 1
    assert len(out["generated_sections"]) == 2
    assert out["generated_sections"][1] == "## 第 2 段\n\n第二段正文"


def test_full_previous_sections_passed_to_llm(
    skill: Skill, full_slots: dict[str, str], section_workflow_step: dict[str, str]
) -> None:
    """生成第 3 段时，应把第 1、2 段全部前文传入 LLM，而不是只传最近 1 段。"""
    outputs = {
        "section_index": 1,
        "generated_sections": ["## 第 1 段\n\n第一段正文", "## 第 2 段\n\n第二段正文"],
        "section_status": "awaiting_confirm",
    }
    with patch.object(skill, "_call_llm", return_value="第三段正文") as mock_llm:
        skill._run(
            workflow_step=section_workflow_step,
            slots=full_slots,
            outputs=outputs,
            user_input="继续",
            user_id="user1",
        )
    system_prompt = mock_llm.call_args[0][0]
    assert "第一段正文" in system_prompt
    assert "第二段正文" in system_prompt
