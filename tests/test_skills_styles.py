"""风格化 Skill 测试。

验证 3 个风格化 Skill（周奇墨 / 徐志胜 / 呼兰）能够被正确加载，
并且生成 Prompt 时确实注入不同的 system prompt。
"""

from unittest.mock import MagicMock

import pytest

from comedy_agent.agents.writer import WriterAgent
from comedy_agent.core.skill_loader import load_skill_config
from comedy_agent.state.schema import ComedyState


@pytest.fixture
def base_state() -> ComedyState:
    return ComedyState(
        user_input="讲讲加班",
        plan={"outline": ["开头", "冲突", "结尾"]},
        current_section=0,
        sections=[],
    )


@pytest.fixture
def mock_llm():
    m = MagicMock()
    m.invoke.return_value = MagicMock(content="mocked section")
    return m


class TestStyleSkillsLoad:
    def test_all_style_skills_load(self):
        for skill_id in ("zhou_qimo", "xu_zhisheng", "hu_lan"):
            cfg = load_skill_config(f"skills/{skill_id}")
            assert cfg is not None, f"{skill_id} 加载失败"
            assert len(cfg.examples) >= 3, f"{skill_id} 示例不足"


class TestStylePrompts:
    def test_zhou_qimo_system_prompt(self, base_state, mock_llm):
        state = base_state.model_copy(update={"selected_skill": "zhou_qimo"})
        agent = WriterAgent()
        agent.run(state, llm=mock_llm)
        system_prompt = mock_llm.invoke.call_args[0][0][0][1]
        assert "周奇墨" in system_prompt or "观察" in system_prompt
        assert "娓娓道来" in system_prompt

    def test_xu_zhisheng_system_prompt(self, base_state, mock_llm):
        state = base_state.model_copy(update={"selected_skill": "xu_zhisheng"})
        agent = WriterAgent()
        agent.run(state, llm=mock_llm)
        system_prompt = mock_llm.invoke.call_args[0][0][0][1]
        assert "徐志胜" in system_prompt or "自嘲" in system_prompt
        assert "高能量" in system_prompt

    def test_hu_lan_system_prompt(self, base_state, mock_llm):
        state = base_state.model_copy(update={"selected_skill": "hu_lan"})
        agent = WriterAgent()
        agent.run(state, llm=mock_llm)
        system_prompt = mock_llm.invoke.call_args[0][0][0][1]
        assert "呼兰" in system_prompt or "隐喻" in system_prompt
        assert "金融" in system_prompt or "职场" in system_prompt

    def test_style_prompts_are_different(self, base_state, mock_llm):
        prompts = []
        for skill_id in ("zhou_qimo", "xu_zhisheng", "hu_lan"):
            state = base_state.model_copy(update={"selected_skill": skill_id})
            agent = WriterAgent()
            agent.run(state, llm=mock_llm)
            system_prompt = mock_llm.invoke.call_args[0][0][0][1]
            prompts.append(system_prompt)

        # 两两比较，至少应该不同
        assert prompts[0] != prompts[1]
        assert prompts[0] != prompts[2]
        assert prompts[1] != prompts[2]

    def test_examples_included_in_prompt(self, base_state, mock_llm):
        state = base_state.model_copy(update={"selected_skill": "zhou_qimo"})
        agent = WriterAgent()
        agent.run(state, llm=mock_llm)
        system_prompt = mock_llm.invoke.call_args[0][0][0][1]
        assert "【参考示例】" in system_prompt
