"""测试高评分内容回流（FeedbackLoop）。"""

from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.documents import Document

from comedy_agent.memory.models import ScriptData
from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.rag.feedback_loop import FeedbackLoop
from comedy_agent.rag.retriever import ComedyRetriever
from comedy_agent.rag.vector_store import VectorStore


class FakeEmbeddings:
    """用于测试的假 Embedding 模型。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] * 10 for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))] * 10


@pytest.fixture
def memory():
    """内存数据库的 UnifiedMemory。"""
    return UnifiedMemory(db_url="sqlite:///:memory:")


@pytest.fixture
def retriever(tmp_path: Path):
    """使用临时持久化路径的检索器。"""
    with patch(
        "comedy_agent.rag.vector_store.ModelFactory.get_embedding_model",
        return_value=FakeEmbeddings(),
    ):
        vs = VectorStore(
            collection_name="test_feedback",
            persist_path=str(tmp_path / "chroma_feedback"),
        )
        return ComedyRetriever(vector_store=vs)


class TestIngestHighRatedScripts:
    """回流主流程测试。"""

    def test_ingest_single_script(self, memory: UnifiedMemory, retriever: ComedyRetriever):
        """单条高评分作品成功回流。"""
        memory.save_script(
            "u001",
            ScriptData(
                title="优秀段子",
                content="这是一个非常搞笑的段子，关于职场加班。",
                script_type="standup",
                rating=4.5,
                tags=["职场", "加班"],
            ),
        )

        loop = FeedbackLoop(memory=memory, retriever=retriever, min_rating=4.0)
        result = loop.ingest_high_rated_scripts(chunk_strategy="paragraph")

        assert result["ingested_scripts"] == 1
        assert result["total_chunks"] >= 1
        assert len(result["script_ids"]) == 1
        assert result["skipped"] == []
        assert result["dry_run"] is False

        # 验证向量库中确实有了
        docs = retriever.vector_store.get_by_filter(
            {"source_script_id": result["script_ids"][0]}
        )
        assert len(docs) > 0
        assert docs[0].metadata.get("feedback_loop") is True

    def test_skip_already_ingested(self, memory: UnifiedMemory, retriever: ComedyRetriever):
        """已入库的作品再次回流时应被跳过。"""
        saved = memory.save_script(
            "u002",
            ScriptData(
                title="经典小品",
                content="经典内容",
                script_type="sketch",
                rating=5.0,
            ),
        )

        loop = FeedbackLoop(memory=memory, retriever=retriever, min_rating=4.0)

        # 第一次回流
        r1 = loop.ingest_high_rated_scripts()
        assert r1["ingested_scripts"] == 1
        assert r1["skipped"] == []

        # 第二次回流
        r2 = loop.ingest_high_rated_scripts()
        assert r2["ingested_scripts"] == 0
        assert r2["skipped"] == [saved.script_id]

    def test_filter_by_min_rating(self, memory: UnifiedMemory, retriever: ComedyRetriever):
        """低于阈值的作品不应被回流。"""
        memory.save_script(
            "u003",
            ScriptData(title="高分", content="高分内容", rating=4.8),
        )
        memory.save_script(
            "u003",
            ScriptData(title="低分", content="低分内容", rating=3.5),
        )

        loop = FeedbackLoop(memory=memory, retriever=retriever, min_rating=4.0)
        result = loop.ingest_high_rated_scripts()

        assert result["ingested_scripts"] == 1
        assert result["script_ids"][0]  # 只有高分作品

    def test_filter_by_user_id(self, memory: UnifiedMemory, retriever: ComedyRetriever):
        """指定 user_id 时只回流该用户的作品。"""
        s1 = memory.save_script(
            "u004",
            ScriptData(title="A的作品", content="内容A", rating=5.0),
        )
        memory.save_script(
            "u005",
            ScriptData(title="B的作品", content="内容B", rating=5.0),
        )

        loop = FeedbackLoop(memory=memory, retriever=retriever, min_rating=4.0)
        result = loop.ingest_high_rated_scripts(user_id="u004")

        assert result["ingested_scripts"] == 1
        assert result["script_ids"] == [s1.script_id]

    def test_dry_run(self, memory: UnifiedMemory, retriever: ComedyRetriever):
        """dry_run 时只统计不入库。"""
        memory.save_script(
            "u006",
            ScriptData(title="测试", content="测试内容", rating=4.5),
        )

        loop = FeedbackLoop(memory=memory, retriever=retriever, min_rating=4.0)
        result = loop.ingest_high_rated_scripts(dry_run=True)

        assert result["dry_run"] is True
        assert result["ingested_scripts"] == 1
        assert result["total_chunks"] >= 1

        # 向量库中应该没有
        assert retriever.vector_store.count() == 0

    def test_no_eligible_scripts(self, memory: UnifiedMemory, retriever: ComedyRetriever):
        """没有符合条件作品时返回空结果。"""
        loop = FeedbackLoop(memory=memory, retriever=retriever, min_rating=4.0)
        result = loop.ingest_high_rated_scripts()

        assert result["ingested_scripts"] == 0
        assert result["total_chunks"] == 0
        assert result["script_ids"] == []


class TestScriptToDocument:
    """作品转 Document 测试。"""

    def test_metadata_enrichment(self):
        script = ScriptData(
            script_id="s001",
            title="标题",
            content="内容",
            script_type="standup",
            rating=4.5,
            tags=["tag1", "tag2"],
        )
        doc = FeedbackLoop._script_to_document(script)

        assert doc.metadata["source_script_id"] == "s001"
        assert doc.metadata["source"] == "user_feedback_loop"
        assert doc.metadata["script_type"] == "standup"
        assert doc.metadata["rating"] == 4.5
        assert doc.metadata["tags"] == ["tag1", "tag2"]
        assert doc.metadata["feedback_loop"] is True
        assert "【标题】" in doc.page_content

    def test_no_title(self):
        script = ScriptData(script_id="s002", content="纯内容")
        doc = FeedbackLoop._script_to_document(script)
        assert doc.page_content == "纯内容"


class TestChunkDocument:
    """分块测试。"""

    def test_paragraph_strategy(self):
        doc = Document(page_content="第一段\n\n第二段\n\n第三段", metadata={})
        chunks = FeedbackLoop._chunk_document(doc, strategy="paragraph")
        assert len(chunks) >= 1

    def test_fixed_strategy(self):
        long_text = "word " * 500
        doc = Document(page_content=long_text, metadata={})
        chunks = FeedbackLoop._chunk_document(doc, strategy="fixed")
        assert len(chunks) > 1
