"""行业数据冷启动 —— 导入首批核心数据到知识库。

提供便捷的批量导入工具，支持从目录自动加载、分块、向量化。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from comedy_agent.core.config import settings
from comedy_agent.rag.chunker import DocumentChunker
from comedy_agent.rag.document_loader import DocumentLoader
from comedy_agent.rag.retriever import ComedyRetriever
from comedy_agent.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# 默认知识库目录
# ------------------------------------------------------------------ #

DEFAULT_KNOWLEDGE_DIR = settings.data_dir / "knowledge"


# ------------------------------------------------------------------ #
# KnowledgeIngestor
# ------------------------------------------------------------------ #


class KnowledgeIngestor:
    """喜剧知识库数据导入器。

    流水线：加载 -> 分块 -> 入库（向量 + BM25）。
    """

    def __init__(
        self,
        retriever: ComedyRetriever | None = None,
        chunk_strategy: str = "paragraph",
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> None:
        """初始化导入器。

        Args:
            retriever: 混合检索器实例，为 ``None`` 时自动创建。
            chunk_strategy: 分块策略，可选 ``fixed`` / ``paragraph`` / ``scene`` / ``dialogue``。
            chunk_size: 分块大小（固定大小策略使用）。
            chunk_overlap: 分块重叠（固定大小策略使用）。
        """
        if retriever is None:
            vector_store = VectorStore(
                collection_name="comedy_knowledge",
                persist_path=str(settings.vector_db_path),
            )
            retriever = ComedyRetriever(vector_store=vector_store)

        self.retriever = retriever
        self.chunk_strategy = chunk_strategy
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # ------------------------------------------------------------------ #
    # 导入入口
    # ------------------------------------------------------------------ #
    def ingest_directory(
        self,
        dir_path: str | Path | None = None,
        pattern: str = "*",
        recursive: bool = True,
    ) -> dict[str, Any]:
        """批量导入目录下的所有支持文件。

        Args:
            dir_path: 知识库目录，默认为 ``data/knowledge/``。
            pattern: glob 匹配模式。
            recursive: 是否递归子目录。

        Returns:
            dict: 导入统计信息。
        """
        path = Path(dir_path) if dir_path else DEFAULT_KNOWLEDGE_DIR
        if not path.exists():
            raise FileNotFoundError(f"知识库目录不存在: {path}")

        logger.info("开始导入知识库: %s", path)

        # 1. 加载文档
        raw_docs = DocumentLoader.load_directory(path, pattern=pattern, recursive=recursive)
        logger.info("加载原始文档 %d 条", len(raw_docs))

        if not raw_docs:
            return {"raw_docs": 0, "chunks": 0, "ingested": 0}

        # 2. 分块
        chunks = self._chunk_documents(raw_docs)
        logger.info("分块后 %d 条", len(chunks))

        # 3. 入库
        self.retriever.ingest(chunks)
        ingested = self.retriever.vector_store.count()

        result = {
            "raw_docs": len(raw_docs),
            "chunks": len(chunks),
            "ingested": ingested,
            "collection": self.retriever.vector_store.collection_name,
        }
        logger.info("导入完成: %s", result)
        return result

    def ingest_file(self, file_path: str | Path) -> dict[str, Any]:
        """导入单个文件。

        Args:
            file_path: 文件路径。

        Returns:
            dict: 导入统计信息。
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        raw_docs = DocumentLoader.load(path)
        chunks = self._chunk_documents(raw_docs)
        self.retriever.ingest(chunks)

        return {
            "raw_docs": len(raw_docs),
            "chunks": len(chunks),
            "ingested": self.retriever.vector_store.count(),
        }

    # ------------------------------------------------------------------ #
    # 分块
    # ------------------------------------------------------------------ #
    def _chunk_documents(self, documents: list[Document]) -> list[Document]:
        """根据策略分块。"""
        if self.chunk_strategy == "fixed":
            return DocumentChunker.split_fixed(
                documents, chunk_size=self.chunk_size, overlap=self.chunk_overlap
            )
        return DocumentChunker.auto_split(documents, strategy=self.chunk_strategy)

    # ------------------------------------------------------------------ #
    # 快捷方法：导入默认知识库
    # ------------------------------------------------------------------ #
    @classmethod
    def ingest_default_knowledge(
        cls,
        retriever: ComedyRetriever | None = None,
    ) -> dict[str, Any]:
        """导入项目内置的默认知识库（data/knowledge/）。"""
        ingestor = cls(retriever=retriever)
        return ingestor.ingest_directory(DEFAULT_KNOWLEDGE_DIR)
