"""Phase 1 端到端验收测试。

验证 v4 核心状态机可以完成“输入主题 → 分析 → 计划 → 逐段写作 →
人类审阅（interrupt）→ 反馈恢复 → 最终输出”的完整创作流程。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langgraph.types import Command

from comedy_agent.graph.builder import build_graph
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def graph():
    """提供编译后的完整状态机 Graph。"""
    return build_graph()


def _make_mock_llm(response_content: str | list[str]) -> MagicMock:
    """构造一个模拟 LLM，支持固定返回值或按次返回值。"""
    llm = MagicMock()
    if isinstance(response_content, list):
        llm.invoke.side_effect = [MagicMock(content=c) for c in response_content]
    else:
        llm.invoke.return_value = MagicMock(content=response_content)
    return llm


def test_full_writing_flow_with_human_in_the_loop(graph):
    """完整创作流程：3 段 outline，逐段通过，最终输出完整文本。"""
    thread_id = "phase1-full-flow"

    analyze_llm = _make_mock_llm(
        '{"topic": "通勤", "attitude": "讽刺", "bias": "无", "emotion": "无奈"}'
    )
    plan_llm = _make_mock_llm(
        '{"todo": ["分析", "写作"], '
        '"outline": ["铺垫通勤烦恼", "展开观察", "callback 收尾"], '
        '"tone": "讽刺"}'
    )
    review_llm = _make_mock_llm(
        '{"decision": "修改", "comments": "再犀利一点", "score": 7}'
    )
    section_texts = [
        "每天早上挤地铁，我都觉得自己像一块被压扁的吐司。",
        "旁边大哥的胳肢窝贴着我脸，我突然理解了什么是‘贴脸开大’。",
        "所以通勤的真正意义，是让你到公司时已经经历了一轮社会的毒打。",
    ]
    write_llm = _make_mock_llm(section_texts)

    with patch("comedy_agent.nodes.analyze_node.ModelFactory") as mock_analyze, \
         patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_plan, \
         patch("comedy_agent.nodes.write_node.ModelFactory") as mock_write, \
         patch("comedy_agent.nodes.review_node.ModelFactory") as mock_review:

        mock_analyze.get_model.return_value = analyze_llm
        mock_plan.get_model.return_value = plan_llm
        mock_write.get_model.return_value = write_llm
        mock_review.get_model.return_value = review_llm

        # 第一次调用：应停在第一段的人类审阅
        result = graph.invoke(
            ComedyState(user_input="写一段关于通勤的脱口秀"),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" in result
        interrupt = result["__interrupt__"][0].value
        assert interrupt["section_text"] == section_texts[0]

        # 逐段通过，直到第三段
        for expected_text in section_texts[1:]:
            result = graph.invoke(
                Command(resume="通过"),
                config={"configurable": {"thread_id": thread_id}},
            )
            assert "__interrupt__" in result
            interrupt = result["__interrupt__"][0].value
            assert interrupt["section_text"] == expected_text

        # 最后一段也通过，进入 finalize
        result = graph.invoke(
            Command(resume="通过"),
            config={"configurable": {"thread_id": thread_id}},
        )

    final_state = ComedyState.model_validate(result)
    assert final_state.phase == "complete"
    assert final_state.output
    for text in section_texts:
        assert text in final_state.output


def test_modify_feedback_rewrites_current_section(graph):
    """用户给出修改意见后，当前段落应被重写并再次暂停等待反馈。"""
    thread_id = "phase1-modify"

    analyze_llm = _make_mock_llm(
        '{"topic": "加班", "attitude": "自嘲", "bias": "无", "emotion": "疲惫"}'
    )
    plan_llm = _make_mock_llm(
        '{"todo": ["分析", "写作"], '
        '"outline": ["开场", "展开"], '
        '"tone": "自嘲"}'
    )
    review_llm = _make_mock_llm(
        '{"decision": "修改", "comments": "太短", "score": 6}'
    )
    first_draft = "加班加到手机都没电了。"
    revised_draft = "加班加到手机都没电了，但我还在回老板消息。"
    write_llm = _make_mock_llm([first_draft, revised_draft])

    with patch("comedy_agent.nodes.analyze_node.ModelFactory") as mock_analyze, \
         patch("comedy_agent.nodes.plan_node.ModelFactory") as mock_plan, \
         patch("comedy_agent.nodes.write_node.ModelFactory") as mock_write, \
         patch("comedy_agent.nodes.review_node.ModelFactory") as mock_review:

        mock_analyze.get_model.return_value = analyze_llm
        mock_plan.get_model.return_value = plan_llm
        mock_write.get_model.return_value = write_llm
        mock_review.get_model.return_value = review_llm

        result = graph.invoke(
            ComedyState(user_input="写一段关于加班的脱口秀"),
            config={"configurable": {"thread_id": thread_id}},
        )
        assert "__interrupt__" in result
        assert result["__interrupt__"][0].value["section_text"] == first_draft

        result = graph.invoke(
            Command(resume="这里再写长一点"),
            config={"configurable": {"thread_id": thread_id}},
        )

    assert "__interrupt__" in result
    assert result["__interrupt__"][0].value["section_text"] == revised_draft
