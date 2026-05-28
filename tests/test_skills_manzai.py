"""ManzaiSkill 单元测试。"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from comedy_agent.skills.manzai import ManzaiSkill


class TestManzaiSkill:
    """测试漫才创作 Skill。"""

    @pytest.fixture
    def mock_llm(self):
        """返回模拟 LLM。"""
        llm = MagicMock()
        llm.invoke.return_value = AIMessage(content="测试漫才对白")
        return llm

    def test_skill_metadata(self):
        """验证 Skill 元数据正确注册。"""
        skill = ManzaiSkill()
        assert skill.name == "manzai_generator"
        assert "漫才" in skill.description

    def test_args_schema(self):
        """验证 args_schema 字段完整。"""
        skill = ManzaiSkill()
        schema = skill.args_schema
        fields = schema.model_fields
        assert "topic" in fields
        assert "duration" in fields
        assert "segments_count" in fields
        assert "absurd_level" in fields
        assert fields["duration"].default == 5
        assert fields["segments_count"].default == 3
        assert fields["absurd_level"].default == "标准"

    def test_build_prompt_structure(self, mock_llm):
        """验证 Prompt 构建包含关键要素。"""
        with patch(
            "comedy_agent.skills.manzai.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = ManzaiSkill()
            prompt_text = skill._build_prompt(
                topic="职场加班",
                duration=5,
                segments_count=4,
                absurd_level="极致",
            )
            assert "职场加班" in prompt_text
            assert "5分钟" in prompt_text
            assert "4段" in prompt_text
            assert "极致" in prompt_text
            assert "（上）" in prompt_text
            assert "突然恢复正常" in prompt_text

    def test_run_returns_content(self, mock_llm):
        """验证 _run 返回 LLM 生成的内容。"""
        mock_llm.return_value = "测试漫才对白"
        with patch(
            "comedy_agent.skills.manzai.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = ManzaiSkill()
            result = skill._run(topic="相亲经历")

            assert isinstance(result, str)
            assert result == "测试漫才对白"
            mock_llm.assert_called_once()

    def test_skill_as_tool(self, mock_llm):
        """验证 Skill 可作为 LangChain Tool 被 invoke。"""
        mock_llm.return_value = "Tool invoke result"
        with patch(
            "comedy_agent.skills.manzai.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = ManzaiSkill()
            result = skill.invoke({"topic": "健身"})

            assert isinstance(result, str)
            assert result == "Tool invoke result"

    def test_arun(self, mock_llm):
        """验证异步接口复用同步逻辑。"""
        import asyncio

        mock_llm.return_value = "async result"
        with patch(
            "comedy_agent.skills.manzai.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = ManzaiSkill()
            result = asyncio.run(skill._arun(topic="AI取代人类"))

            assert result == "async result"
