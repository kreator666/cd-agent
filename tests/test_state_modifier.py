"""state_modifier 动态 Prompt 构建器测试。"""

from pathlib import Path

import pytest

from comedy_agent.core.annotation import AnnotatedExample
from comedy_agent.core.knowledge_models import KnowledgeItem
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


    def test_knowledge_in_system_prompt(self, sample_state, sample_skill):
        knowledge = [
            KnowledgeItem(
                id="three-setup-four-punch",
                title="三番四抖",
                category="technique",
                content="三番四抖是相声经典结构技巧。",
                summary="通过三次铺垫和一次转折制造笑点。",
            )
        ]
        system_prompt, _ = build_prompts(
            sample_state, sample_skill, retrieved_knowledge=knowledge
        )
        assert "【理论知识参考】" in system_prompt
        assert "三番四抖" in system_prompt

    def test_topic_variable_replaced_from_analysis(self, sample_state):
        """Skill prompt_template 中的 {topic} 应被 analysis/slots 中的话题替换。"""
        skill = SkillConfig(
            id="with_topic",
            name="With Topic",
            system_prompt="",
            prompt_template="请创作关于「{topic}」的段子。",
            skill_dir=Path("."),
        )
        sample_state.analysis = {
            "topic": "假如我有三千万",
            "attitude": "自嘲",
            "bias": "无",
            "emotion": "荒诞",
        }
        _, user_prompt = build_prompts(sample_state, skill)
        assert "假如我有三千万" in user_prompt
        assert "{topic}" not in user_prompt

    def test_topic_variable_falls_back_to_slots(self, sample_state):
        """analysis 为空时，{topic} 应回退到 slots 中的话题。"""
        skill = SkillConfig(
            id="with_topic",
            name="With Topic",
            system_prompt="",
            prompt_template="请创作关于「{topic}」的段子。",
            skill_dir=Path("."),
        )
        sample_state.analysis = None
        sample_state.slots = {"话题": "假如我有三千万"}
        _, user_prompt = build_prompts(sample_state, skill)
        assert "假如我有三千万" in user_prompt
        assert "{topic}" not in user_prompt

    def test_attitude_bias_emotion_and_duration_replaced(self, sample_state):
        """Skill 模板中的态度、偏见、情绪、时长占位符应被替换。"""
        skill = SkillConfig(
            id="with_all",
            name="With All",
            system_prompt="",
            prompt_template=(
                "话题：{topic}，态度：{attitude}，偏见：{bias}，情绪：{emotion}，时长：{duration}分钟"
            ),
            skill_dir=Path("."),
        )
        sample_state.analysis = {
            "topic": "三千万",
            "attitude": "自嘲",
            "bias": "无",
            "emotion": "荒诞",
        }
        sample_state.duration = 5
        _, user_prompt = build_prompts(sample_state, skill)
        assert "话题：三千万" in user_prompt
        assert "态度：自嘲" in user_prompt
        assert "偏见：无" in user_prompt
        assert "情绪：荒诞" in user_prompt
        assert "时长：5分钟" in user_prompt

    def test_search_context_in_system_prompt(self, sample_state, sample_skill):
        """state.knowledge_context 应被注入 system prompt。"""
        sample_state.knowledge_context = [
            {
                "title": "搜索：内卷",
                "category": "search",
                "content": "内卷指过度竞争导致边际收益下降。",
                "summary": "内卷指过度竞争导致边际收益下降。",
                "source": "duckduckgo",
            }
        ]
        system_prompt, _ = build_prompts(sample_state, sample_skill)
        assert "【搜索资料参考】" in system_prompt
        assert "内卷指过度竞争" in system_prompt

    def test_standup_skill_prompt_is_segment_aware(self, sample_state):
        """standup Skill 的 prompt 应包含逐段写作指令和上下文变量。"""
        from comedy_agent.core.config import settings
        from comedy_agent.core.skill_loader import load_skill_config

        skill = load_skill_config(settings.skills_dir / "standup")
        assert skill is not None
        assert skill.id == "standup"

        sample_state.analysis = {
            "topic": "职场加班",
            "attitude": "讽刺",
            "bias": "无",
            "emotion": "愤怒",
        }
        sample_state.duration = 5
        sample_state.plan = {"outline": ["开场铺垫", "冲突升级", "收尾callback"]}
        sample_state.current_section = 1
        sample_state.sections = ["这是已经完成的开场段落。"]
        sample_state.feedback = ""
        sample_state.selected_skill = "standup"

        system_prompt, user_prompt = build_prompts(sample_state, skill)
        assert "逐段" in system_prompt
        assert "当前段落" in system_prompt
        assert "已完成段落" in system_prompt
        assert "不要提前写未来段落" in system_prompt
        assert "当前段落目标" in user_prompt
        assert "冲突升级" in user_prompt
        assert "这是已经完成的开场段落" in user_prompt
        assert "话题：职场加班" in user_prompt
        assert "态度：讽刺" in user_prompt
        assert "时长：约 5 分钟" in user_prompt
        assert "{section_goal}" not in user_prompt
        assert "{completed_sections}" not in user_prompt
