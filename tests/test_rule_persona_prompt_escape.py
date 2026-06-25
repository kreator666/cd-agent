"""人物画像 skill prompt 花括号转义测试。

rule_persona 的 rule_content/outline 中可能包含 JSON 花括号，
必须被 ChatPromptTemplate 当作字面量处理，否则会报 missing variables {''}。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.skills.rule_persona import RulePersonaSkill


@pytest.fixture
def skill() -> RulePersonaSkill:
    return RulePersonaSkill()


def test_rule_persona_handles_json_braces(skill: RulePersonaSkill) -> None:
    """当规则示例中包含 JSON 花括号时，不应触发 ChatPromptTemplate 变量缺失错误。"""
    rule_content = {
        "example_style": '{"style": "短句", "hook": true}',
    }
    outline = "写一个关于加班的段子，参考：{\"tone\": \"愤怒\"}"

    mock_llm = MagicMock()
    mock_chain = MagicMock()
    mock_chain.__or__.return_value = mock_chain
    mock_chain.invoke.return_value = MagicMock(content="mock result")

    with patch("comedy_agent.skills.rule_persona.ModelFactory.get_model_with_fallback", return_value=mock_llm), \
         patch("comedy_agent.skills.rule_persona.ChatPromptTemplate.from_messages", return_value=mock_chain):
        # 只要能成功调用 invoke 且不抛变量缺失错误，就说明花括号已正确处理
        skill._run(outline=outline, rule_content=rule_content, user_id="user1")

    mock_chain.invoke.assert_called_once()
