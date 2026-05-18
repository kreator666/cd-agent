"""测试向量数据库（ChromaDB + Embedding）。"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from comedy_agent.rag.vector_store import VectorStore, _sanitize_metadata


class FakeEmbeddings:
    """用于测试的假 Embedding 模型。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] * 10 for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))] * 10


@pytest.fixture
def vector_store(tmp_path: Path):
    """创建临时向量存储（内存模式）。"""
    with patch(
        "comedy_agent.rag.vector_store.ModelFactory.get_embedding_model",
        return_value=FakeEmbeddings(),
    ):
        store = VectorStore(
            collection_name="test_comedy",
            persist_path=str(tmp_path / "chroma_test"),
        )
        yield store
        store.clear()


class TestSanitizeMetadata:
    """元数据清理测试。"""

    def test_basic_types(self):
        meta = {"s": "str", "i": 1, "f": 1.5, "b": True}
        assert _sanitize_metadata(meta) == meta

    def test_path_converted(self):
        meta = {"path": Path("test.txt")}
        result = _sanitize_metadata(meta)
        assert result["path"] == "test.txt"

    def test_none_converted(self):
        meta = {"empty": None}
        assert _sanitize_metadata(meta)["empty"] == ""

    def test_nested_list(self):
        meta = {"tags": ["a", "b", 1]}
        assert _sanitize_metadata(meta)["tags"] == ["a", "b", 1]


class TestVectorStore:
    """VectorStore 集成测试。"""

    def test_add_and_search(self, vector_store: VectorStore):
        docs = [
            Document(page_content="相声的三番四抖技巧", metadata={"category": "theory"}),
            Document(page_content="脱口秀关于职场加班", metadata={"category": "script"}),
            Document(page_content="小品创作结构分析", metadata={"category": "theory"}),
        ]
        ids = vector_store.add_documents(docs)
        assert len(ids) == 3
        assert vector_store.count() == 3

        # 搜索
        results = vector_store.search("相声技巧", top_k=2)
        assert len(results) <= 2
        assert all(isinstance(r, Document) for r in results)
        # 结果中应包含距离信息
        assert "distance" in results[0].metadata

    def test_search_with_filter(self, vector_store: VectorStore):
        docs = [
            Document(page_content="理论一", metadata={"category": "theory"}),
            Document(page_content="剧本一", metadata={"category": "script"}),
        ]
        vector_store.add_documents(docs)

        results = vector_store.search("内容", top_k=10, filter_dict={"category": "theory"})
        assert len(results) == 1
        assert results[0].metadata.get("category") == "theory"

    def test_delete_and_count(self, vector_store: VectorStore):
        docs = [Document(page_content="待删除", metadata={})]
        ids = vector_store.add_documents(docs)
        assert vector_store.count() == 1

        vector_store.delete(ids)
        assert vector_store.count() == 0

    def test_clear(self, vector_store: VectorStore):
        docs = [Document(page_content="清空测试", metadata={})]
        vector_store.add_documents(docs)
        assert vector_store.count() == 1

        vector_store.clear()
        assert vector_store.count() == 0

    def test_peek(self, vector_store: VectorStore):
        docs = [
            Document(page_content="doc1", metadata={"id": 1}),
            Document(page_content="doc2", metadata={"id": 2}),
        ]
        vector_store.add_documents(docs)
        peeked = vector_store.peek(limit=2)
        assert len(peeked) == 2

    def test_add_empty_list(self, vector_store: VectorStore):
        ids = vector_store.add_documents([])
        assert ids == []
        assert vector_store.count() == 0

    def test_document_id_in_metadata(self, vector_store: VectorStore):
        docs = [Document(page_content="id test", metadata={})]
        ids = vector_store.add_documents(docs)
        results = vector_store.search("id test", top_k=1)
        assert results[0].metadata["doc_id"] == ids[0]
