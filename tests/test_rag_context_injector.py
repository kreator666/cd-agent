"""测试上下文注入机制。"""

from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from comedy_agent.rag.context_injector import ContextInjector, _estimate_tokens


class TestEstimateTokens:
    """Token 估算测试。"""

    def test_empty(self):
        assert _estimate_tokens("") == 0

    def test_english(self):
        # "hello world" ~ 11 chars * 0.25 = 2.75 -> 3
        assert _estimate_tokens("hello world") >= 2

    def test_chinese(self):
        # "相声技巧" ~ 4 chars * 1.5 = 6
        assert _estimate_tokens("相声技巧") == 6

    def test_mixed(self):
        text = "相声 stand-up"
        tokens = _estimate_tokens(text)
        # 2 中文字 + 7 英文字符(含空格和连字符) = 2*1.5 + 7*0.25 = 3 + 1.75 = 4.75 -> 5
        assert tokens == 5


class MockRetriever:
    """假检索器。"""

    def __init__(self, docs: list[Document] | None = None):
        self.docs = docs or []

    def retrieve(self, query: str, top_k: int = 5) -> list[Document]:
        return self.docs[:top_k]


class TestContextInjector:
    """ContextInjector 测试。"""

    def test_inject_with_system_prompt(self):
        docs = [
            Document(page_content="三番四抖是相声经典结构", metadata={"source": "喜剧的艺术"}),
            Document(page_content="脱口秀需要观察生活", metadata={"source": "创作指南"}),
        ]
        injector = ContextInjector(
            retriever=MockRetriever(docs),
            max_context_tokens=1000,
            format_style="reference",
        )
        result = injector.inject("相声结构", system_prompt="你是喜剧助手")

        assert "你是喜剧助手" in result["system_prompt"]
        assert "知识库参考" in result["system_prompt"]
        assert "三番四抖" in result["context"]
        assert "喜剧的艺术" in result["context"]

    def test_inject_without_system_prompt(self):
        docs = [Document(page_content="知识点", metadata={})]
        injector = ContextInjector(retriever=MockRetriever(docs))
        result = injector.inject("查询")

        assert result["system_prompt"] == ""
        assert "知识点" in result["context"]

    def test_inject_no_results(self):
        injector = ContextInjector(retriever=MockRetriever([]))
        result = injector.inject("查询", system_prompt="助手")

        assert result["system_prompt"] == "助手"
        assert result["context"] == ""

    def test_format_list(self):
        docs = [
            Document(page_content="第一点", metadata={}),
            Document(page_content="第二点", metadata={}),
        ]
        injector = ContextInjector(
            retriever=MockRetriever(docs), format_style="list"
        )
        result = injector.inject("查询")
        assert result["context"].startswith("- 第一点")
        assert "- 第二点" in result["context"]

    def test_format_summary(self):
        docs = [
            Document(page_content="段落一", metadata={}),
            Document(page_content="段落二", metadata={}),
        ]
        injector = ContextInjector(
            retriever=MockRetriever(docs), format_style="summary"
        )
        result = injector.inject("查询")
        assert "段落一" in result["context"]
        assert "段落二" in result["context"]

    def test_truncate_to_budget(self):
        long_text = "这是一个很长的句子。" * 200  # ~3600 chars, mostly Chinese
        docs = [Document(page_content=long_text, metadata={})]
        injector = ContextInjector(
            retriever=MockRetriever(docs),
            max_context_tokens=50,
        )
        result = injector.inject("查询")
        assert "...（以下内容因 Token 预算限制已截断）" in result["context"]
        # 截断后应远小于原文
        assert len(result["context"]) < len(long_text) * 0.3

    def test_build_messages_with_system(self):
        docs = [Document(page_content="知识", metadata={})]
        injector = ContextInjector(
            retriever=MockRetriever(docs),
            max_context_tokens=1000,
        )
        messages = injector.build_messages(
            query="问题",
            system_prompt="系统提示",
            chat_history=[("human", "历史问题")],
        )
        assert messages[0] == ("system", messages[0][1])
        assert "系统提示" in messages[0][1]
        assert messages[1] == ("human", "历史问题")
        assert messages[2] == ("human", "问题")

    def test_build_messages_without_system(self):
        docs = [Document(page_content="知识", metadata={})]
        injector = ContextInjector(retriever=MockRetriever(docs))
        messages = injector.build_messages(query="问题")
        assert messages[0] == ("human", messages[0][1])
        assert "参考知识" in messages[0][1]
        assert "问题" in messages[0][1]
