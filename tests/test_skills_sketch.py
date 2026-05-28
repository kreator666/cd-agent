"""SketchSkill 单元测试。"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from comedy_agent.skills.sketch import SketchSkill


class TestSketchSkill:
    """测试小品创作 Skill。"""

    @pytest.fixture
    def mock_llm(self):
        """返回模拟 LLM。"""
        llm = MagicMock()
        llm.invoke.return_value = AIMessage(content="测试小品剧本")
        return llm

    def test_skill_metadata(self):
        """验证 Skill 元数据正确注册。"""
        skill = SketchSkill()
        assert skill.name == "sketch_generator"
        assert "小品" in skill.description

    def test_args_schema(self):
        """验证 args_schema 字段完整。"""
        skill = SketchSkill()
        schema = skill.args_schema
        fields = schema.model_fields
        assert "theme" in fields
        assert "characters_count" in fields
        assert "setting" in fields
        assert "duration" in fields
        assert "conflict_type" in fields
        assert fields["characters_count"].default == 3
        assert fields["setting"].default == "家庭"
        assert fields["duration"].default == 8
        assert fields["conflict_type"].default == "执念vs现实"

    def test_build_prompt_structure(self, mock_llm):
        """验证 Prompt 构建包含关键要素。"""
        with patch(
            "comedy_agent.skills.sketch.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = SketchSkill()
            prompt_text = skill._build_prompt(
                theme="家庭聚餐",
                characters_count=4,
                setting="家庭",
                duration=10,
                conflict_type="执念vs执念",
            )
            assert "家庭聚餐" in prompt_text
            assert "4人" in prompt_text
            assert "家庭" in prompt_text
            assert "10分钟" in prompt_text
            assert "执念vs执念" in prompt_text
            assert "核心执念" in prompt_text
            assert "肢体喜剧" in prompt_text

    def test_run_returns_content(self, mock_llm):
        """验证 _run 返回 LLM 生成的内容。"""
        mock_llm.return_value = "测试小品剧本"
        with patch(
            "comedy_agent.skills.sketch.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = SketchSkill()
            result = skill._run(theme="面试遭遇")

            assert isinstance(result, str)
            assert result == "测试小品剧本"
            mock_llm.assert_called_once()

    def test_skill_as_tool(self, mock_llm):
        """验证 Skill 可作为 LangChain Tool 被 invoke。"""
        mock_llm.return_value = "Tool invoke result"
        with patch(
            "comedy_agent.skills.sketch.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = SketchSkill()
            result = skill.invoke({"theme": "医院看病"})

            assert isinstance(result, str)
            assert result == "Tool invoke result"

    def test_arun(self, mock_llm):
        """验证异步接口复用同步逻辑。"""
        import asyncio

        mock_llm.return_value = "async result"
        with patch(
            "comedy_agent.skills.sketch.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = SketchSkill()
            result = asyncio.run(skill._arun(theme="校园生活"))

            assert result == "async result"
