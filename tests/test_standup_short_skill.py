"""standup_short Skill 测试 —— 加载发现、系统提示硬约束、invoke 调用链。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from langchain_core.language_models.fake_chat_models import FakeListChatModel

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "standup_short"


class _FakeChatModel(FakeListChatModel):
    """记录输入并返回固定内容的假 LLM。"""

    received_messages: Any = None

    def __init__(self, content: str) -> None:
        super().__init__(responses=[content])

    def invoke(self, input, config=None, *, stop=None, **kwargs):  # noqa: A002
        self.received_messages = input
        return super().invoke(input, config=config, stop=stop, **kwargs)


@pytest.fixture
def loaded_skill():
    from comedy_agent.skills.loader import load_single_skill

    skill = load_single_skill(SKILL_DIR)
    assert skill is not None, "standup_short Skill 加载失败"
    return skill


class TestSkillDiscovery:
    """Skill 按名字发现测试。"""

    def test_load_single_skill_by_name(self, loaded_skill):
        assert loaded_skill.name == "standup_short"
        assert "短视频" in loaded_skill.description

    def test_discovered_by_plugin_scan(self):
        from comedy_agent.skills.loader import load_plugin_skills

        skills_dir = SKILL_DIR.parent
        names = [s.name for s in load_plugin_skills(skills_dir)]
        assert "standup_short" in names
        # 不影响既有 Skill
        assert "standup_focused" in names

    def test_args_schema_compatible_with_standup_focused(self, loaded_skill):
        schema = loaded_skill.args_schema
        fields = schema.model_fields
        for key in ("topic", "attitude", "bias", "emotion"):
            assert key in fields, f"缺少参数 {key}"
        assert "duration" in fields  # 可接受


class TestSystemPromptHardConstraints:
    """系统提示必须包含 30 秒 / 字数上限 / 结构标签等硬约束。"""

    def test_system_prompt_contains_hard_constraints(self, loaded_skill):
        prompt = loaded_skill.SYSTEM_PROMPT
        assert "30 秒" in prompt
        assert "100~150 字" in prompt
        assert "180 字" in prompt
        assert "爆梗" in prompt

    def test_system_prompt_contains_section_labels(self, loaded_skill):
        prompt = loaded_skill.SYSTEM_PROMPT
        for label in ("【铺垫】", "【升级】", "【爆梗】", "【收尾】"):
            assert label in prompt, f"系统提示缺少结构标签 {label}"

    def test_template_md_exists_and_covers_spec(self):
        text = (SKILL_DIR / "template.md").read_text(encoding="utf-8")
        assert "30 秒" in text
        assert "180" in text
        for label in ("【铺垫】", "【升级】", "【爆梗】", "【收尾】"):
            assert label in text


class TestInvokeWithMockedLLM:
    """invoke 调用链：mock LLM 后返回渲染结果。"""

    def test_invoke_renders_template_and_returns_llm_output(self, loaded_skill):
        from comedy_agent.models.factory import ModelFactory

        fake_llm = _FakeChatModel("【铺垫】测试正文")

        with patch.object(
            ModelFactory,
            "get_model_with_fallback",
            return_value=fake_llm,
        ):
            output = loaded_skill.invoke(
                {
                    "topic": "加班",
                    "attitude": "自嘲",
                    "bias": "无",
                    "emotion": "荒诞",
                    "duration": 3,
                }
            )

        assert output == "【铺垫】测试正文"

        messages = fake_llm.received_messages.to_messages()
        assert messages is not None
        system_text = str(messages[0].content)
        human_text = str(messages[1].content)

        # 系统提示在终稿模式下附加输出硬约束
        for label in ("【铺垫】", "【升级】", "【爆梗】", "【收尾】"):
            assert label in system_text
        assert "180 字" in system_text

        # 用户提示渲染了四维度输入
        assert "加班" in human_text
        assert "自嘲" in human_text
        assert "荒诞" in human_text

    def test_invoke_ignores_duration(self, loaded_skill):
        from comedy_agent.models.factory import ModelFactory

        fake_llm = _FakeChatModel("ok")

        with patch.object(
            ModelFactory,
            "get_model_with_fallback",
            return_value=fake_llm,
        ):
            output = loaded_skill.invoke(
                {
                    "topic": "相亲",
                    "attitude": "吐槽",
                    "bias": "无",
                    "emotion": "尴尬",
                    "duration": 10,
                }
            )

        assert output == "ok"
        human_text = str(fake_llm.received_messages.to_messages()[1].content)
        assert "相亲" in human_text
