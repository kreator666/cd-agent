"""测试记忆与 RAG 融合注入。

验证 ContextInjector 和 AgentOrchestrator 能同时注入用户记忆上下文
与知识库检索上下文。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from comedy_agent.agent.orchestrator import AgentOrchestrator
from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.rag.context_injector import ContextInjector


class TestContextInjectorMemory:
    """ContextInjector 记忆 + 知识融合测试。"""

    @pytest.fixture
    def injector(self) -> ContextInjector:
        """提供带 mock retriever 的 ContextInjector。"""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            Document(
                page_content="三番四抖是相声的基本技巧。",
                metadata={"source": "comedy_theory.md"},
            ),
        ]
        return ContextInjector(retriever=mock_retriever, max_context_tokens=2000)

    def test_inject_with_memory_and_knowledge(self, injector: ContextInjector) -> None:
        """同时注入记忆上下文和知识上下文。"""
        result = injector.inject(
            query="怎么写段子",
            system_prompt="你是一个喜剧助手。",
            memory_context="用户喜欢黑色幽默，讨厌谐音梗。",
        )
        assert "【关于用户】" in result["system_prompt"]
        assert "用户喜欢黑色幽默" in result["system_prompt"]
        assert "【知识库参考】" in result["system_prompt"]
        assert "三番四抖" in result["system_prompt"]

    def test_inject_memory_only(self, injector: ContextInjector) -> None:
        """仅注入记忆（无知识检索结果）。"""
        injector.retriever.retrieve.return_value = []
        result = injector.inject(
            query="hello",
            system_prompt="你是一个喜剧助手。",
            memory_context="用户偏好黑色幽默。",
        )
        assert "【关于用户】" in result["system_prompt"]
        assert "用户偏好黑色幽默" in result["system_prompt"]
        assert "【知识库参考】" not in result["system_prompt"]

    def test_inject_knowledge_only(self, injector: ContextInjector) -> None:
        """仅注入知识（无记忆）。"""
        result = injector.inject(
            query="怎么写段子",
            system_prompt="你是一个喜剧助手。",
        )
        assert "【知识库参考】" in result["system_prompt"]
        assert "【关于用户】" not in result["system_prompt"]

    def test_inject_no_system_prompt(self, injector: ContextInjector) -> None:
        """无 system_prompt 时，记忆和知识放在 context 中。"""
        result = injector.inject(
            query="怎么写段子",
            memory_context="用户偏好黑色幽默。",
        )
        assert result["system_prompt"] == ""
        assert "三番四抖" in result["context"]

    def test_build_messages_with_memory(self, injector: ContextInjector) -> None:
        """build_messages 同时注入记忆和知识。"""
        messages = injector.build_messages(
            query="怎么写段子",
            system_prompt="你是一个喜剧助手。",
            memory_context="用户喜欢黑色幽默。",
        )
        assert messages[0][0] == "system"
        assert "【关于用户】" in messages[0][1]
        assert "【知识库参考】" in messages[0][1]
        assert messages[-1][0] == "human"
        assert messages[-1][1] == "怎么写段子"


class TestOrchestratorMemoryIntegration:
    """AgentOrchestrator 记忆集成测试。"""

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.bind_tools = MagicMock(return_value=llm)
        return llm

    def test_run_with_user_id_injects_memory(self, mock_llm) -> None:
        """传入 user_id 时，Orchestrator 应注入用户记忆。"""
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
                        AIMessage(content="hi"),
                        AIMessage(content="answer"),
                    ]
                }
                mock_create.return_value = mock_agent

                # 使用内存数据库的 UnifiedMemory
                memory = UnifiedMemory(db_url="sqlite:///:memory:")
                memory.save_preference("u001", "style", "black_humor")

                orch = AgentOrchestrator(memory=memory)
                result = orch.run("hello", user_id="u001")

                assert result["output"] == "answer"
                call_args = mock_agent.invoke.call_args[0][0]
                messages = call_args["messages"]
                assert messages[0][0] == "system"
                assert "【关于用户】" in messages[0][1]
                assert "black_humor" in messages[0][1]

    def test_run_without_user_id_no_memory(self, mock_llm) -> None:
        """未传入 user_id 时，不应注入记忆。"""
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
                        AIMessage(content="hi"),
                        AIMessage(content="answer"),
                    ]
                }
                mock_create.return_value = mock_agent

                memory = UnifiedMemory(db_url="sqlite:///:memory:")
                memory.save_preference("u002", "style", "satire")

                orch = AgentOrchestrator(memory=memory)
                result = orch.run("hello")

                assert result["output"] == "answer"
                call_args = mock_agent.invoke.call_args[0][0]
                messages = call_args["messages"]
                # 有 system prompt 但没有记忆部分
                assert messages[0][0] == "system"
                assert "【关于用户】" not in messages[0][1]

    def test_run_with_memory_none(self, mock_llm) -> None:
        """未配置 memory 时，正常运行。"""
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
                        AIMessage(content="hi"),
                        AIMessage(content="answer"),
                    ]
                }
                mock_create.return_value = mock_agent

                orch = AgentOrchestrator(memory=None)
                result = orch.run("hello", user_id="u003")

                assert result["output"] == "answer"
                call_args = mock_agent.invoke.call_args[0][0]
                messages = call_args["messages"]
                assert "【关于用户】" not in messages[0][1]
