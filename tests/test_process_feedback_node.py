"""process_feedback_node 单元测试。"""

from __future__ import annotations

import pytest

from comedy_agent.nodes.process_feedback_node import process_feedback_node
from comedy_agent.state.schema import ComedyState


def test_approve_moves_to_next_section():
    state = ComedyState(
        feedback="通过",
        current_section=0,
        plan={"outline": ["a", "b", "c"]},
    )
    result = process_feedback_node(state)
    assert result["phase"] == "writing"
    assert result["current_section"] == 1


def test_approve_last_section_finalizes():
    state = ComedyState(
        feedback="通过",
        current_section=2,
        plan={"outline": ["a", "b", "c"]},
    )
    result = process_feedback_node(state)
    assert result["phase"] == "finalizing"
    assert result["current_section"] == 3


def test_modify_rewrites_current_section():
    state = ComedyState(
        feedback="这里再讽刺一点",
        current_section=1,
        plan={"outline": ["a", "b", "c"]},
    )
    result = process_feedback_node(state)
    assert result["phase"] == "writing"
    assert result["current_section"] == 1
    assert result["feedback"] == "这里再讽刺一点"


def test_manual_edit_adopts_edited_text_and_moves_on():
    state = ComedyState(
        feedback="[manual]\n编辑后的段落内容",
        current_section=0,
        sections=["原段落"],
        plan={"outline": ["a", "b"]},
    )
    result = process_feedback_node(state)
    assert result["phase"] == "writing"
    assert result["current_section"] == 1
    assert result["sections"][0] == "编辑后的段落内容"


def test_manual_edit_on_last_section_finalizes():
    state = ComedyState(
        feedback="[manual]\n最后一段编辑版",
        current_section=1,
        sections=["第一段", "第二段原"],
        plan={"outline": ["a", "b"]},
    )
    result = process_feedback_node(state)
    assert result["phase"] == "finalizing"
    assert result["sections"][1] == "最后一段编辑版"
