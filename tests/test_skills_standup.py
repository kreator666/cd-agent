"""StandupSkill 单元测试。"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from comedy_agent.skills.standup import StandupSkill


class TestStandupSkill:
    """测试脱口秀创作 Skill。"""

    @pytest.fixture
    def mock_llm(self):
        """返回模拟 LLM。"""
        llm = MagicMock()
        llm.invoke.return_value = AIMessage(
            content="测试段子内容\n\n这是主体部分。\n\nCallback！"
        )
        return llm

    def test_skill_metadata(self):
        """验证 Skill 元数据正确注册。"""
        skill = StandupSkill()
        assert skill.name == "standup_generator"
        assert "脱口秀" in skill.description
        assert "预期违背" in skill.description

    def test_args_schema(self):
        """验证 args_schema 字段完整。"""
        skill = StandupSkill()
        schema = skill.args_schema
        fields = schema.model_fields
        assert "topic" in fields
        assert "style" in fields
        assert "duration" in fields
        assert "audience" in fields
        assert "density" in fields
        assert "perspective_count" in fields
        # 默认值检查
        assert fields["style"].default == "日常观察"
        assert fields["duration"].default == 3
        assert fields["audience"].default == "通用"
        assert fields["density"].default == "标准"
        assert fields["perspective_count"].default == 2

    def test_build_prompt_structure(self, mock_llm):
        """验证 Prompt 构建包含关键要素。"""
        with patch(
            "comedy_agent.skills.standup.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = StandupSkill()
            prompt_text = skill._build_user_prompt(
                topic="职场加班",
                style="自嘲",
                duration=5,
                audience="互联网从业者",
                density="密集",
                perspective_count=3,
            )
            assert "职场加班" in prompt_text
            assert "自嘲" in prompt_text
            assert "5分钟" in prompt_text
            assert "互联网从业者" in prompt_text
            assert "密集" in prompt_text
            assert "3 个不同视角" in prompt_text

    def test_run_returns_content(self, mock_llm):
        """验证 _run 返回 LLM 生成的内容。"""
        # MagicMock 被 LangChain 当作 RunnableLambda 调用，
        # 所以检查 mock_llm() 而非 mock_llm.invoke()
        mock_llm.return_value = "测试段子内容\n\n这是主体部分。\n\nCallback！"
        with patch(
            "comedy_agent.skills.standup.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = StandupSkill()
            result = skill._run(topic="相亲经历")

            assert isinstance(result, str)
            assert result == "测试段子内容\n\n这是主体部分。\n\nCallback！"
            mock_llm.assert_called_once()

    def test_run_invokes_with_prompt(self, mock_llm):
        """验证调用链路使用了正确 Prompt 结构。

        由于 MagicMock 被 LangChain 包装为 RunnableLambda，
        实际调用的是 mock_llm() 而非 mock_llm.invoke()。
        我们通过 patch ChatPromptTemplate 来验证 prompt 构建。
        """
        from langchain_core.prompts import ChatPromptTemplate

        captured_messages = None

        original_from_messages = ChatPromptTemplate.from_messages

        def capture_from_messages(msgs):
            nonlocal captured_messages
            prompt = original_from_messages(msgs)
            captured_messages = msgs
            return prompt

        with patch(
            "comedy_agent.skills.standup.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            with patch.object(ChatPromptTemplate, "from_messages", side_effect=capture_from_messages):
                skill = StandupSkill()
                skill._run(topic="AI取代人类")

                assert captured_messages is not None
                assert len(captured_messages) == 2
                assert captured_messages[0][0] == "system"
                assert captured_messages[1][0] == "human"
                assert "AI取代人类" in captured_messages[1][1]

    def test_skill_as_tool(self, mock_llm):
        """验证 Skill 可作为 LangChain Tool 被 invoke。"""
        mock_llm.return_value = "Tool invoke result"
        with patch(
            "comedy_agent.skills.standup.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = StandupSkill()
            # Tool.invoke 是 BaseTool 的标准接口
            result = skill.invoke({"topic": "房价"})

            assert isinstance(result, str)
            assert result == "Tool invoke result"

    def test_arun(self, mock_llm):
        """验证异步接口复用同步逻辑。"""
        import asyncio

        mock_llm.return_value = "async result"
        with patch(
            "comedy_agent.skills.standup.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            skill = StandupSkill()
            result = asyncio.run(skill._arun(topic="健身"))

            assert result == "async result"

    def test_knowledge_injection(self, mock_llm):
        """验证传入 user_id 时 Skill 会在 system prompt 中注入知识库。"""
        from langchain_core.documents import Document
        from langchain_core.prompts import ChatPromptTemplate

        captured_messages = None
        original_from_messages = ChatPromptTemplate.from_messages

        def capture_from_messages(msgs):
            nonlocal captured_messages
            prompt = original_from_messages(msgs)
            captured_messages = msgs
            return prompt

        mock_llm.return_value = "result with knowledge"
        with patch(
            "comedy_agent.skills.standup.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            with patch.object(ChatPromptTemplate, "from_messages", side_effect=capture_from_messages):
                skill = StandupSkill()
                # 注入 mock retriever
                mock_retriever = MagicMock()
                mock_retriever.retrieve.return_value = [
                    Document(page_content="测试知识：脱口秀需要开场钩子", metadata={"source": "test.pdf"})
                ]
                skill.retriever = mock_retriever

                skill._run(topic="职场", user_id="test_user")

                assert captured_messages is not None
                system_msg = captured_messages[0][1]
                assert "【知识库参考】" in system_msg
                assert "测试知识：脱口秀需要开场钩子" in system_msg
                assert "test.pdf" in system_msg

    def test_knowledge_injection_disabled_without_user_id(self, mock_llm):
        """验证不传 user_id 且 retriever 为 None 时不会注入知识库。"""
        from langchain_core.prompts import ChatPromptTemplate

        captured_messages = None
        original_from_messages = ChatPromptTemplate.from_messages

        def capture_from_messages(msgs):
            nonlocal captured_messages
            prompt = original_from_messages(msgs)
            captured_messages = msgs
            return prompt

        mock_llm.return_value = "result without knowledge"
        with patch(
            "comedy_agent.skills.standup.ModelFactory.get_model_with_fallback",
            return_value=mock_llm,
        ):
            with patch.object(ChatPromptTemplate, "from_messages", side_effect=capture_from_messages):
                skill = StandupSkill()
                skill.retriever = None
                skill._run(topic="职场")

                assert captured_messages is not None
                system_msg = captured_messages[0][1]
                assert "【知识库参考】" not in system_msg
