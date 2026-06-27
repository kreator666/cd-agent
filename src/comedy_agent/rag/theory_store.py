"""理论知识向量库存储。

基于现有 VectorStore（ChromaDB）之上封装 `comedy_theory` 集合，
提供知识条目的入库与检索接口。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.documents import Document

from comedy_agent.core.knowledge_models import KnowledgeItem
from comedy_agent.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

THEORY_COLLECTION = "comedy_theory"


def _item_to_document(item: KnowledgeItem) -> Document:
    """把 KnowledgeItem 转为可入库的 Document。"""
    return Document(
        page_content=item.embedding_text or item.build_embedding_text(),
        metadata={
            "id": item.id,
            "title": item.title,
            "category": item.category,
            "source": item.source,
            "item_json": item.model_dump_json(ensure_ascii=False),
        },
    )


def _document_to_item(doc: Document) -> KnowledgeItem:
    """从检索返回的 Document 还原 KnowledgeItem。"""
    meta = doc.metadata or {}
    item_json = meta.get("item_json")
    if item_json:
        try:
            return KnowledgeItem.model_validate_json(str(item_json))
        except Exception:
            logger.warning("知识条目 JSON 解析失败，使用字段回退还原: %s", meta.get("title"))

    return KnowledgeItem(
        id=meta.get("id", ""),
        title=meta.get("title", ""),
        category=meta.get("category", "concept"),  # type: ignore[arg-type]
        content=doc.page_content,
        source=meta.get("source", ""),
        embedding_text=doc.page_content,
    )


class TheoryStore:
    """喜剧理论知识向量库。

    默认使用集合名 ``comedy_theory``，支持按 ``category`` 过滤检索。
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedding_model_name: str | None = None,
    ) -> None:
        """初始化理论知识库。

        Args:
            vector_store: 外部传入的 VectorStore 实例；为 None 时新建。
            embedding_model_name: 新建 VectorStore 时使用的 Embedding 模型名。
        """
        if vector_store is not None:
            self.vector_store = vector_store
        else:
            self.vector_store = VectorStore(
                collection_name=THEORY_COLLECTION,
                embedding_model_name=embedding_model_name,
            )

    def ingest(self, items: list[KnowledgeItem]) -> list[str]:
        """把知识条目批量写入向量库。

        Args:
            items: 要入库的 KnowledgeItem 列表。

        Returns:
            写入的文档 ID 列表。
        """
        if not items:
            return []
        documents = [_item_to_document(item) for item in items]
        ids = [item.id for item in items]
        return self.vector_store.add_documents(documents, ids=ids)

    def search(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 5,
    ) -> list[KnowledgeItem]:
        """检索与查询最相关的理论知识。

        Args:
            query: 查询文本。
            category: 按类别过滤（concept / technique / pattern / rule）。
            top_k: 返回结果数量。

        Returns:
            按相似度排序的 KnowledgeItem 列表。
        """
        filter_dict: dict[str, Any] | None = None
        if category:
            filter_dict = {"category": category}

        docs = self.vector_store.search(query, top_k=top_k, filter_dict=filter_dict)
        return [_document_to_item(doc) for doc in docs]

    def get_by_id(self, item_id: str) -> KnowledgeItem | None:
        """按 ID 精确获取知识条目。"""
        docs = self.vector_store.get_by_filter({"id": item_id})
        if docs:
            return _document_to_item(docs[0])
        return None

    def count(self) -> int:
        """返回集合中文档数量。"""
        return self.vector_store.count()

    def clear(self) -> None:
        """清空理论知识集合。"""
        self.vector_store.clear()
