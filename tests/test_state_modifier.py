"""state_modifier 动态 Prompt 构建器测试。"""

from pathlib import Path

import pytest

from comedy_agent.core.annotation import AnnotatedExample
from comedy_agent.core.skill_loader import SkillConfig
from comedy_agent.graph.state_modifier import build_prompts
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def sample_skill() -> SkillConfig:
    return SkillConfig(
        id="test_skill",
        name="Test Skill",
        description="For testing",
        task_type="creative",
        system_prompt="你是 {{ style }} 风格的写手。",
        prompt_template="写第 {{ section_index }} 段：{{ section_goal }}",
        examples=[],
        styles=[],
        metadata={},
        skill_dir=Path("."),
    )


@pytest.fixture
def sample_state() -> ComedyState:
    return ComedyState(
        user_input="讲讲上班",
        plan={"outline": ["开头", "冲突", "结尾"]},
        current_section=1,
        sections=["第一段内容"],
        feedback="再口语化一点",
        selected_skill="test_skill",
        selected_style="自嘲",
    )


class TestBuildPrompts:
    def test_system_prompt_contains_skill_and_style(self, sample_state, sample_skill):
        system_prompt, _ = build_prompts(sample_state, sample_skill)
        assert "中文喜剧创作助手" in system_prompt
        assert "你是 自嘲 风格的写手" in system_prompt

    def test_user_prompt_contains_context(self, sample_state, sample_skill):
        _, user_prompt = build_prompts(sample_state, sample_skill)
        assert "写第 2 段" in user_prompt
        assert "冲突" in user_prompt

    def test_examples_in_system_prompt(self, sample_state):
        skill = SkillConfig(
            id="with_examples",
            name="With Examples",
            system_prompt="",
            examples=[
                {"input": "主题：旅行", "output": "我旅行从来不带脑子。"}
            ],
            skill_dir=Path("."),
        )
        system_prompt, _ = build_prompts(sample_state, skill)
        assert "【参考示例】" in system_prompt
        assert "我旅行从来不带脑子" in system_prompt

    def test_dynamic_examples_in_system_prompt(self, sample_state, sample_skill):
        retrieved = [
            AnnotatedExample(
                content="动态示例文本",
                setup="动态铺垫",
                punchline="动态笑点",
                topic="上班",
                style="自嘲",
                tags=["职场"],
            )
        ]
        system_prompt, _ = build_prompts(
            sample_state, sample_skill, retrieved_examples=retrieved
        )
        assert "动态铺垫" in system_prompt
        assert "动态笑点" in system_prompt
        assert "职场" in system_prompt

    def test_no_feedback_section_when_empty(self, sample_state, sample_skill):
        sample_state.feedback = ""
        _, user_prompt = build_prompts(sample_state, sample_skill)
        assert "人类审阅反馈" not in user_prompt

    def test_default_user_prompt_when_skill_has_no_template(self, sample_state):
        skill = SkillConfig(
            id="no_template",
            name="No Template",
            system_prompt="",
            skill_dir=Path("."),
        )
        _, user_prompt = build_prompts(sample_state, skill)
        assert "整体计划" in user_prompt
        assert "当前段落目标" in user_prompt
