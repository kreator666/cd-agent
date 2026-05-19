"""AgentOrchestrator 单元测试。"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from comedy_agent.agent.orchestrator import AgentOrchestrator


class TestAgentOrchestrator:
    """测试 Agent 主控的注册、构建与执行。"""

    @pytest.fixture
    def mock_llm(self):
        """提供一个 Mock LLM。"""
        llm = MagicMock()
        llm.bind_tools = MagicMock(return_value=llm)
        return llm

    @pytest.fixture
    def dummy_skill(self):
        """提供一个 dummy Skill。"""

        @tool
        def dummy_hello(query: str) -> str:
            """Say hello for testing."""
            return f"Hello {query}"

        return dummy_hello

    # ------------------------------------------------------------------ #
    # Skill 管理
    # ------------------------------------------------------------------ #
    def test_register_skill(self, mock_llm, dummy_skill):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            orch = AgentOrchestrator()
            orch.register_skill(dummy_skill)

    def test_register_skill_updates_list(self, mock_llm, dummy_skill):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            orch = AgentOrchestrator()
            orch.register_skill(dummy_skill)
            assert orch.list_skills() == ["dummy_hello"]

    def test_list_skills_empty_by_default(self, mock_llm):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            orch = AgentOrchestrator()
            assert orch.list_skills() == []

    # ------------------------------------------------------------------ #
    # Agent 构建
    # ------------------------------------------------------------------ #
    def test_build_agent_without_tools(self, mock_llm):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            with patch(
                "comedy_agent.agent.orchestrator.create_agent"
            ) as mock_create:
                mock_agent = MagicMock()
                mock_create.return_value = mock_agent

                orch = AgentOrchestrator()
                agent = orch._build_agent()

                mock_create.assert_called_once()
                assert agent is mock_agent

    def test_build_agent_with_tools(self, mock_llm, dummy_skill):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            with patch(
                "comedy_agent.agent.orchestrator.create_agent"
            ) as mock_create:
                mock_agent = MagicMock()
                mock_create.return_value = mock_agent

                orch = AgentOrchestrator()
                orch.register_skill(dummy_skill)
                orch._build_agent()

                _, kwargs = mock_create.call_args
                assert kwargs["tools"] == [dummy_skill]

    def test_build_agent_cached(self, mock_llm):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            with patch(
                "comedy_agent.agent.orchestrator.create_agent"
            ) as mock_create:
                mock_agent = MagicMock()
                mock_create.return_value = mock_agent

                orch = AgentOrchestrator()
                orch._build_agent()
                orch._build_agent()  # 第二次调用应复用缓存

                mock_create.assert_called_once()

    def test_register_invalidates_cache(self, mock_llm, dummy_skill):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            with patch(
                "comedy_agent.agent.orchestrator.create_agent"
            ) as mock_create:
                mock_create.return_value = MagicMock()

                orch = AgentOrchestrator()
                orch._build_agent()
                orch.register_skill(dummy_skill)

                assert orch._agent is None

    # ------------------------------------------------------------------ #
    # 执行
    # ------------------------------------------------------------------ #
    def test_run_without_tools(self, mock_llm):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            with patch(
                "comedy_agent.agent.orchestrator.create_agent"
            ) as mock_create:
                mock_agent = MagicMock()
                mock_agent.invoke.return_value = {
                    "messages": [
                        HumanMessage(content="hi"),
                        AIMessage(content="Hello there"),
                    ]
                }
                mock_create.return_value = mock_agent

                orch = AgentOrchestrator()
                result = orch.run("hi")

                assert result["output"] == "Hello there"
                assert len(result["messages"]) == 2
                mock_agent.invoke.assert_called_once_with(
                    {
                        "messages": [
                            ("system", mock_create.call_args.kwargs["system_prompt"]),
                            ("human", "hi"),
                        ]
                    }
                )

    def test_run_with_chat_history(self, mock_llm):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            with patch(
                "comedy_agent.agent.orchestrator.create_agent"
            ) as mock_create:
                mock_agent = MagicMock()
                mock_agent.invoke.return_value = {
                    "messages": [
                        HumanMessage(content="prev"),
                        AIMessage(content="ok"),
                        HumanMessage(content="next"),
                        AIMessage(content="final"),
                    ]
                }
                mock_create.return_value = mock_agent

                orch = AgentOrchestrator()
                result = orch.run(
                    "next",
                    chat_history=[("human", "prev"), ("ai", "ok")],
                )

                assert result["output"] == "final"
                call_args = mock_agent.invoke.call_args
                messages = call_args[0][0]["messages"]
                assert messages == [
                    ("system", mock_create.call_args.kwargs["system_prompt"]),
                    ("human", "prev"),
                    ("ai", "ok"),
                    ("human", "next"),
                ]

    def test_run_extracts_last_ai_message(self, mock_llm):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            with patch(
                "comedy_agent.agent.orchestrator.create_agent"
            ) as mock_create:
                mock_agent = MagicMock()
                mock_agent.invoke.return_value = {
                    "messages": [
                        HumanMessage(content="q"),
                        AIMessage(content="first"),
                        HumanMessage(content="q2"),
                        AIMessage(content="second"),
                    ]
                }
                mock_create.return_value = mock_agent

                orch = AgentOrchestrator()
                result = orch.run("q2")

                assert result["output"] == "second"

    def test_custom_system_prompt(self, mock_llm):
        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            with patch(
                "comedy_agent.agent.orchestrator.create_agent"
            ) as mock_create:
                mock_create.return_value = MagicMock()

                custom_prompt = "Custom system prompt"
                orch = AgentOrchestrator(system_prompt=custom_prompt)
                orch._build_agent()

                _, kwargs = mock_create.call_args
                assert kwargs["system_prompt"] == custom_prompt

    # ------------------------------------------------------------------ #
    # 异步
    # ------------------------------------------------------------------ #
    def test_arun(self, mock_llm):
        import asyncio
        from unittest.mock import AsyncMock

        with patch(
            "comedy_agent.agent.orchestrator.ModelFactory.get_model",
            return_value=mock_llm,
        ):
            with patch(
                "comedy_agent.agent.orchestrator.create_agent"
            ) as mock_create:
                mock_agent = MagicMock()
                mock_agent.ainvoke = AsyncMock(return_value={
                    "messages": [
                        HumanMessage(content="async q"),
                        AIMessage(content="async answer"),
                    ]
                })
                mock_create.return_value = mock_agent

                orch = AgentOrchestrator()
                result = asyncio.run(orch.arun("async q"))

                assert result["output"] == "async answer"
                mock_agent.ainvoke.assert_awaited_once()
