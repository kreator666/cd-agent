"""Skill 路由器测试。"""

import pytest

from comedy_agent.core.skill_router import resolve_skill
from comedy_agent.state.schema import ComedyState


class TestResolveSkill:
    def test_defaults_to_standup(self):
        state = ComedyState(user_input="hello")
        result = resolve_skill(state)
        assert result["selected_skill"] == "standup"
        assert result["selected_style"] is None

    def test_explicit_skill_id(self):
        state = ComedyState(user_input="hello")
        result = resolve_skill(state, explicit_skill_id="standup")
        assert result["selected_skill"] == "standup"

    def test_mention_alias(self):
        state = ComedyState(user_input="@脱口秀 讲一段")
        result = resolve_skill(state)
        assert result["selected_skill"] == "standup"

    def test_preserve_existing_state(self):
        state = ComedyState(
            user_input="继续",
            selected_skill="standup",
            selected_style="自嘲",
        )
        result = resolve_skill(state)
        assert result["selected_skill"] == "standup"
        assert result["selected_style"] == "自嘲"

    def test_explicit_style_overrides_state(self):
        state = ComedyState(
            user_input="hello",
            selected_style="旧风格",
        )
        result = resolve_skill(state, explicit_style="新风格")
        assert result["selected_style"] == "新风格"

    def test_unknown_skill_fallback(self):
        state = ComedyState(user_input="hello")
        result = resolve_skill(state, explicit_skill_id="not_a_skill")
        assert result["selected_skill"] == "standup"

    def test_slot_mention_ignored(self):
        state = ComedyState(user_input="@话题 人工智能")
        result = resolve_skill(state)
        assert result["selected_skill"] == "standup"
