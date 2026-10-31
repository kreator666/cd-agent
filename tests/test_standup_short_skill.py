"""standup_short Skill 测试 —— 加载发现、系统提示硬约束、故事结构注入、invoke 调用链。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from langchain_core.language_models.fake_chat_models import FakeListChatModel

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "standup_short"

STRUCTURE_NAMES = ["铺垫-反转", "三番四抖", "雪球效应", "弹簧魔鬼", "归谬滑坡"]
# 各结构标志词（用于断言"只注入所选结构"）
_STRUCTURE_MARKERS = {
    "setup_punchline": "加固",
    "san_fan_si_dou": "第四抖",
    "snowball": "雪崩",
    "spring_devil": "弹簧魔鬼",
    "reductio": "归谬",
}


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


def _invoke_and_get_messages(loaded_skill, fake_llm: _FakeChatModel, **kwargs) -> tuple[str, str]:
    """mock LLM 后 invoke，返回 (system_text, human_text)。"""
    from comedy_agent.models.factory import ModelFactory

    with patch.object(
        ModelFactory,
        "get_model_with_fallback",
        return_value=fake_llm,
    ):
        loaded_skill.invoke(kwargs)

    messages = fake_llm.received_messages.to_messages()
    assert messages is not None
    return str(messages[0].content), str(messages[1].content)


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
        assert "structure" in fields  # 新增故事结构参数
        assert fields["structure"].default == "random"


class TestSystemPromptHardConstraints:
    """系统提示必须包含 30 秒 / 字数上限 / mini callback 等全局硬约束。"""

    def test_system_prompt_contains_hard_constraints(self, loaded_skill):
        prompt = loaded_skill.SYSTEM_PROMPT
        assert "30 秒" in prompt
        assert "100~150 字" in prompt
        assert "300 字" in prompt
        assert "爆梗" in prompt
        assert "mini callback" in prompt

    def test_system_prompt_has_no_fixed_structure(self, loaded_skill):
        """全局提示词不再写死固定分段结构，结构由各结构文件定义。"""
        prompt = loaded_skill.SYSTEM_PROMPT
        for label in ("【铺垫】", "【升级】", "【爆梗】", "【收尾】"):
            assert label not in prompt, f"系统提示不应包含固定结构标签 {label}"
        # 全局提示词不包含任何具体结构素材（省 token：只注入所选结构）
        for name in STRUCTURE_NAMES:
            assert name not in prompt

    def test_structure_files_exist_and_use_section_labels(self):
        for key in _STRUCTURE_MARKERS:
            path = SKILL_DIR / "structures" / f"{key}.md"
            assert path.is_file(), f"缺少结构文件 {path}"
            text = path.read_text(encoding="utf-8")
            assert "【】" in text or "【" in text  # 分段标签格式
            assert _STRUCTURE_MARKERS[key] in text
            # 每个文件控制在 40 行以内
            assert len(text.splitlines()) <= 40

    def test_template_md_exists_and_covers_spec(self):
        text = (SKILL_DIR / "template.md").read_text(encoding="utf-8")
        assert "30 秒" in text
        assert "300" in text
        for key in _STRUCTURE_MARKERS:
            assert key in text


class TestStructureInjection:
    """structure 参数：只注入所选结构的提示词。"""

    def test_specific_structure_only_injected(self, loaded_skill):
        fake_llm = _FakeChatModel("ok")
        system_text, human_text = _invoke_and_get_messages(
            loaded_skill,
            fake_llm,
            topic="加班",
            attitude="自嘲",
            bias="无",
            emotion="荒诞",
            duration=3,
            structure="snowball",
        )

        # 用户提示包含所选结构名与其标志词
        assert "雪球效应" in human_text
        assert "雪崩" in human_text
        # 不含其他结构的名称与标志词
        assert "弹簧魔鬼" not in human_text
        assert "归谬" not in human_text
        assert "三番" not in human_text
        # 结构素材只注入用户提示，不进系统提示（系统提示保持精简）
        assert "雪球效应" not in system_text

    def test_random_structure_picks_one_valid_structure(self, loaded_skill):
        fake_llm = _FakeChatModel("ok")
        system_text, human_text = _invoke_and_get_messages(
            loaded_skill,
            fake_llm,
            topic="加班",
            attitude="自嘲",
            bias="无",
            emotion="荒诞",
            duration=3,
            structure="random",
        )

        assert "# 故事结构：" in human_text
        matched = [name for name in STRUCTURE_NAMES if name in human_text]
        assert len(matched) == 1, f"应随机选中恰好一个结构，实际: {matched}"

    def test_random_is_default_when_omitted(self, loaded_skill):
        fake_llm = _FakeChatModel("ok")
        _, human_text = _invoke_and_get_messages(
            loaded_skill,
            fake_llm,
            topic="加班",
            attitude="自嘲",
            bias="无",
            emotion="荒诞",
            duration=3,
        )

        assert "# 故事结构：" in human_text
        matched = [name for name in STRUCTURE_NAMES if name in human_text]
        assert len(matched) == 1

    def test_invalid_structure_falls_back_to_random(self, loaded_skill):
        fake_llm = _FakeChatModel("ok")
        _, human_text = _invoke_and_get_messages(
            loaded_skill,
            fake_llm,
            topic="加班",
            attitude="自嘲",
            bias="无",
            emotion="荒诞",
            duration=3,
            structure="not-a-structure",
        )

        # 兜底为随机：提示词仍是合法结构，且不含非法值本身
        assert "# 故事结构：" in human_text
        assert "not-a-structure" not in human_text
        matched = [name for name in STRUCTURE_NAMES if name in human_text]
        assert len(matched) == 1


class TestInvokeWithMockedLLM:
    """invoke 调用链：mock LLM 后返回渲染结果。"""

    def test_invoke_renders_template_and_returns_llm_output(self, loaded_skill):
        fake_llm = _FakeChatModel("【铺垫】测试正文")
        system_text, human_text = _invoke_and_get_messages(
            loaded_skill,
            fake_llm,
            topic="加班",
            attitude="自嘲",
            bias="无",
            emotion="荒诞",
            duration=3,
        )

        assert fake_llm.received_messages is not None

        # 系统提示在终稿模式下附加输出硬约束（300 字上限、结构标签随所选结构）
        assert "300 字" in system_text

        # 用户提示渲染了四维度输入
        assert "加班" in human_text
        assert "自嘲" in human_text
        assert "荒诞" in human_text

    def test_invoke_ignores_duration(self, loaded_skill):
        fake_llm = _FakeChatModel("ok")
        _, human_text = _invoke_and_get_messages(
            loaded_skill,
            fake_llm,
            topic="相亲",
            attitude="吐槽",
            bias="无",
            emotion="尴尬",
            duration=10,
        )

        assert "相亲" in human_text
