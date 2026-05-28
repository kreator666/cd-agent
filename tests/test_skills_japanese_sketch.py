"""JapaneseSketchSkill 单元测试。"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from comedy_agent.skills.japanese_sketch import JapaneseSketchSkill


class TestJapaneseSketchSkill:
    """测试日式短剧创作 Skill。"""

    @pytest.fixture
    def mock_llm(self):
        """返回模拟 LLM。"""
        llm = MagicMock()
        llm.invoke.return_value = AIMessage(content="测试日式短剧剧本")
        return llm

    def test_skill_metadata(self):
        """验证 Skill 元数据正确注册。"""
        skill = JapaneseSketchSkill()
        assert skill.name == "japanese_sketch_generator"
        assert "短剧" in skill.description

    def test_args_schema(self):
        """验证 args_schema 字段完整。"""
        skill = JapaneseSketchSkill()
        schema = skill.args_schema
        fields = schema.model_fields
        assert "theme" in fields
        assert "characters_count" in fields
        assert "setting" in fields
        assert "duration" in fields
        assert "character_type" in fields
        assert "punchline_density" in fields
        assert fields["characters_count"].default == 2
        assert fields["setting"].default == "便利店"
        assert fields["duration"].default == 5
        assert fields["character_type"].default == "偏执"
        assert fields["punchline_density"].default == 4

    def test_build_prompt_structure(self, mock_llm):
        """验证 Prompt 构建包含关键要素。"""
        with patch(
            "comedy_agent.skills.japanese_sketch.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = JapaneseSketchSkill()
            prompt_text = skill._build_prompt(
                theme="便利店打工",
                characters_count=3,
                setting="便利店",
                duration=5,
                character_type="自大",
                punchline_density=6,
            )
            assert "便利店打工" in prompt_text
            assert "3人" in prompt_text
            assert "便利店" in prompt_text
            assert "5分钟" in prompt_text
            assert "自大" in prompt_text
            assert "6个/分钟" in prompt_text
            assert "【笑点" in prompt_text

    def test_run_returns_content(self, mock_llm):
        """验证 _run 返回 LLM 生成的内容。"""
        mock_llm.return_value = "测试日式短剧剧本"
        with patch(
            "comedy_agent.skills.japanese_sketch.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = JapaneseSketchSkill()
            result = skill._run(theme="医院看病")

            assert isinstance(result, str)
            assert result == "测试日式短剧剧本"
            mock_llm.assert_called_once()

    def test_skill_as_tool(self, mock_llm):
        """验证 Skill 可作为 LangChain Tool 被 invoke。"""
        mock_llm.return_value = "Tool invoke result"
        with patch(
            "comedy_agent.skills.japanese_sketch.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = JapaneseSketchSkill()
            result = skill.invoke({"theme": "办公室"})

            assert isinstance(result, str)
            assert result == "Tool invoke result"

    def test_arun(self, mock_llm):
        """验证异步接口复用同步逻辑。"""
        import asyncio

        mock_llm.return_value = "async result"
        with patch(
            "comedy_agent.skills.japanese_sketch.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = JapaneseSketchSkill()
            result = asyncio.run(skill._arun(theme="餐厅"))

            assert result == "async result"
