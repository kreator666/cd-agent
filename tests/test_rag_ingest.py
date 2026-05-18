"""测试知识库数据导入工具。"""

from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.documents import Document

from comedy_agent.rag.ingest import KnowledgeIngestor


class FakeEmbeddings:
    """用于测试的假 Embedding 模型。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] * 10 for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))] * 10


@pytest.fixture
def ingestor(tmp_path: Path):
    """创建使用临时持久化路径的导入器。"""
    with patch(
        "comedy_agent.rag.vector_store.ModelFactory.get_embedding_model",
        return_value=FakeEmbeddings(),
    ):
        from comedy_agent.rag.vector_store import VectorStore
        from comedy_agent.rag.retriever import ComedyRetriever

        vs = VectorStore(
            collection_name="test_ingest",
            persist_path=str(tmp_path / "chroma_ingest"),
        )
        retriever = ComedyRetriever(vector_store=vs)
        return KnowledgeIngestor(retriever=retriever, chunk_strategy="paragraph")


class TestIngestDirectory:
    """批量目录导入测试。"""

    def test_ingest_txt_files(self, ingestor: KnowledgeIngestor, tmp_path: Path):
        (tmp_path / "a.txt").write_text("Document A content.", encoding="utf-8")
        (tmp_path / "b.txt").write_text("Document B content.", encoding="utf-8")

        result = ingestor.ingest_directory(tmp_path, pattern="*.txt")
        assert result["raw_docs"] == 2
        assert result["chunks"] >= 1
        assert result["ingested"] >= 1
        assert result["collection"] == "test_ingest"

    def test_ingest_empty_directory(self, ingestor: KnowledgeIngestor, tmp_path: Path):
        result = ingestor.ingest_directory(tmp_path)
        assert result["raw_docs"] == 0
        assert result["chunks"] == 0
        assert result["ingested"] == 0

    def test_ingest_not_found(self, ingestor: KnowledgeIngestor):
        with pytest.raises(FileNotFoundError):
            ingestor.ingest_directory("/nonexistent/path")

    def test_ingest_recursive(self, ingestor: KnowledgeIngestor, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "root.md").write_text("Root doc", encoding="utf-8")
        (sub / "deep.md").write_text("Deep doc", encoding="utf-8")

        result = ingestor.ingest_directory(tmp_path, pattern="*.md", recursive=True)
        assert result["raw_docs"] == 2

    def test_ingest_non_recursive(self, ingestor: KnowledgeIngestor, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "root.md").write_text("Root doc", encoding="utf-8")
        (sub / "deep.md").write_text("Deep doc", encoding="utf-8")

        result = ingestor.ingest_directory(tmp_path, pattern="*.md", recursive=False)
        assert result["raw_docs"] == 1


class TestIngestFile:
    """单文件导入测试。"""

    def test_ingest_single_file(self, ingestor: KnowledgeIngestor, tmp_path: Path):
        fp = tmp_path / "single.md"
        fp.write_text("# Title\n\nBody text.", encoding="utf-8")

        result = ingestor.ingest_file(fp)
        assert result["raw_docs"] == 1
        assert result["chunks"] >= 1
        assert result["ingested"] >= 1

    def test_ingest_file_not_found(self, ingestor: KnowledgeIngestor):
        with pytest.raises(FileNotFoundError):
            ingestor.ingest_file("/nonexistent/file.txt")


class TestIngestDefaultKnowledge:
    """导入内置默认知识库测试。"""

    def test_ingest_default(self, tmp_path: Path):
        with patch(
            "comedy_agent.rag.vector_store.ModelFactory.get_embedding_model",
            return_value=FakeEmbeddings(),
        ):
            from comedy_agent.rag.vector_store import VectorStore
            from comedy_agent.rag.retriever import ComedyRetriever

            vs = VectorStore(
                collection_name="test_default",
                persist_path=str(tmp_path / "chroma_default"),
            )
            retriever = ComedyRetriever(vector_store=vs)
            result = KnowledgeIngestor.ingest_default_knowledge(retriever=retriever)
            assert result["raw_docs"] > 0
            assert result["chunks"] > 0
            assert result["ingested"] > 0


class TestChunkStrategy:
    """分块策略测试。"""

    def test_fixed_strategy(self, tmp_path: Path):
        with patch(
            "comedy_agent.rag.vector_store.ModelFactory.get_embedding_model",
            return_value=FakeEmbeddings(),
        ):
            from comedy_agent.rag.vector_store import VectorStore
            from comedy_agent.rag.retriever import ComedyRetriever

            vs = VectorStore(
                collection_name="test_fixed",
                persist_path=str(tmp_path / "chroma_fixed"),
            )
            retriever = ComedyRetriever(vector_store=vs)
            ingestor = KnowledgeIngestor(
                retriever=retriever,
                chunk_strategy="fixed",
                chunk_size=50,
                chunk_overlap=10,
            )
            fp = tmp_path / "long.txt"
            fp.write_text("word " * 100, encoding="utf-8")
            result = ingestor.ingest_file(fp)
            assert result["chunks"] > 1  # 长文本应被拆成多块
