"""测试混合检索（向量 + BM25 + Cross-Encoder）。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from comedy_agent.rag.retriever import ComedyRetriever, _simple_tokenize


class TestSimpleTokenizer:
    """简单分词器测试。"""

    def test_chinese_chars(self):
        tokens = _simple_tokenize("相声技巧")
        assert tokens == ["相", "声", "技", "巧"]

    def test_english_words(self):
        tokens = _simple_tokenize("Hello world")
        assert "hello" in tokens
        assert "world" in tokens

    def test_mixed(self):
        tokens = _simple_tokenize("相声 stand-up comedy")
        assert "相" in tokens
        assert "声" in tokens
        assert "stand-up" in tokens
        assert "comedy" in tokens


class FakeVectorStore:
    """假向量存储，用于测试。"""

    def __init__(self):
        self.docs: list[Document] = []

    def add_documents(self, documents: list[Document]) -> list[str]:
        self.docs.extend(documents)
        return [str(i) for i in range(len(self.docs))]

    def search(self, query: str, top_k: int = 5) -> list[Document]:
        # 简单模拟：返回包含查询词的文档
        return [
            Document(page_content=d.page_content, metadata={**d.metadata, "doc_id": f"vec_{i}"})
            for i, d in enumerate(self.docs)
            if query in d.page_content
        ][:top_k]

    def clear(self) -> None:
        self.docs.clear()

    def count(self) -> int:
        return len(self.docs)


@pytest.fixture
def fake_vs():
    return FakeVectorStore()


class TestBM25Only:
    """仅 BM25 检索测试（无 Cross-Encoder）。"""

    def test_ingest_and_retrieve(self, fake_vs: FakeVectorStore):
        retriever = ComedyRetriever(vector_store=fake_vs)
        docs = [
            Document(page_content="相声的三番四抖技巧", metadata={"cat": "theory"}),
            Document(page_content="脱口秀创作方法论", metadata={"cat": "theory"}),
            Document(page_content="小品剧本结构", metadata={"cat": "script"}),
        ]
        retriever.ingest(docs)

        results = retriever.retrieve("相声技巧", top_k=2)
        assert len(results) <= 2
        # 至少有一个结果包含"相声"
        assert any("相声" in r.page_content for r in results)

    def test_filter_by_bm25_score(self, fake_vs: FakeVectorStore):
        retriever = ComedyRetriever(vector_store=fake_vs)
        retriever.ingest([Document(page_content="相声", metadata={})])
        # 查询不相关的内容，BM25 分数为 0，不应返回
        results = retriever.retrieve("abcdefgh", top_k=5)
        assert len(results) == 0

    def test_merge_deduplication(self, fake_vs: FakeVectorStore):
        retriever = ComedyRetriever(vector_store=fake_vs)
        docs = [Document(page_content="唯一文档", metadata={})]
        retriever.ingest(docs)

        # 向量检索和 BM25 都会返回同一文档，应去重
        results = retriever.retrieve("唯一文档", top_k=5)
        assert len(results) == 1

    def test_clear(self, fake_vs: FakeVectorStore):
        retriever = ComedyRetriever(vector_store=fake_vs)
        retriever.ingest([Document(page_content="test", metadata={})])
        assert retriever.vector_store.count() == 1

        retriever.clear()
        assert retriever.vector_store.count() == 0
        assert retriever._bm25 is None


class TestWithMockCrossEncoder:
    """带 Mock Cross-Encoder 的测试。"""

    def test_rerank_order(self, fake_vs: FakeVectorStore):
        retriever = ComedyRetriever(vector_store=fake_vs)
        docs = [
            Document(page_content="关于相声的技巧", metadata={}),
            Document(page_content="关于相声的历史", metadata={}),
        ]
        retriever.ingest(docs)

        # mock CrossEncoder：让第二个文档得分更高
        def mock_predict(pairs):
            return [0.3, 0.8]

        with patch(
            "comedy_agent.rag.retriever.CrossEncoder",
            return_value=MagicMock(predict=mock_predict),
        ):
            results = retriever.retrieve("相声", top_k=2)
            assert len(results) == 2
            # 重排序后，得分高的（第二个文档）应排在前面
            assert "历史" in results[0].page_content
            assert results[0].metadata.get("rerank_score") == 0.8

    def test_rerank_top_k_limit(self, fake_vs: FakeVectorStore):
        retriever = ComedyRetriever(vector_store=fake_vs)
        docs = [Document(page_content=f"doc{i}", metadata={}) for i in range(10)]
        retriever.ingest(docs)

        with patch(
            "comedy_agent.rag.retriever.CrossEncoder",
            return_value=MagicMock(predict=lambda pairs: list(range(len(pairs)))),
        ):
            results = retriever.retrieve("doc", top_k=3)
            assert len(results) == 3

    def test_rerank_metadata_preservation(self, fake_vs: FakeVectorStore):
        retriever = ComedyRetriever(vector_store=fake_vs)
        docs = [Document(page_content="test", metadata={"source": "book"})]
        retriever.ingest(docs)

        with patch(
            "comedy_agent.rag.retriever.CrossEncoder",
            return_value=MagicMock(predict=lambda pairs: [0.9]),
        ):
            results = retriever.retrieve("test", top_k=1)
            assert results[0].metadata["source"] == "book"
            assert "rerank_score" in results[0].metadata
