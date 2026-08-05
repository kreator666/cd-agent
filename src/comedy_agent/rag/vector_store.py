"""向量数据库搭建 —— ChromaDB + Embedding 接入。

封装 ChromaDB 客户端，提供文档入库、向量检索、集合管理能力。
Embedding 通过 ModelFactory 统一获取，支持配置化切换。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_core.documents import Document

from comedy_agent.models.factory import ModelFactory
from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# ChromaDB 导入（延迟导入避免初始化开销）
# ------------------------------------------------------------------ #

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    _HAS_CHROMADB = True
except ImportError:  # pragma: no cover
    _HAS_CHROMADB = False
    logger.warning("chromadb 未安装，向量数据库不可用")


# ------------------------------------------------------------------ #
# VectorStore
# ------------------------------------------------------------------ #


class VectorStore:
    """喜剧知识库向量存储。

    基于 ChromaDB，支持内存模式（开发）与持久化模式（生产）。
    """

    def __init__(
        self,
        collection_name: str = "comedy_knowledge",
        persist_path: str | None = None,
        embedding_model_name: str | None = None,
    ) -> None:
        """初始化向量存储。

        Args:
            collection_name: ChromaDB 集合名称。
            persist_path: 持久化路径，为 ``None`` 时使用内存模式（开发）。
            embedding_model_name: Embedding 模型标识，为 ``None`` 时使用默认模型。
        """
        if not _HAS_CHROMADB:
            raise ImportError("chromadb 未安装，请运行: pip install chromadb")

        self.collection_name = collection_name
        self.persist_path = persist_path or settings.vector_db_path
        self.embedding_model_name = embedding_model_name

        # 初始化 ChromaDB 客户端
        if self.persist_path:
            self.client = chromadb.PersistentClient(
                path=str(self.persist_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
            self.client = chromadb.Client(
                settings=ChromaSettings(anonymized_telemetry=False)
            )

        self.collection = self.client.get_or_create_collection(
            name=self.collection_name
        )

        # 初始化 Embedding 模型（容错：连接失败时记录错误，不阻塞启动）
        self._embedding = None
        try:
            self._embedding = ModelFactory.get_embedding_model(embedding_model_name)
        except Exception as e:
            logger.error(
                "Embedding 模型 '%s' 初始化失败: %s。向量检索与入库功能将不可用。",
                embedding_model_name or settings.default_embedding_model,
                e,
            )

    # ------------------------------------------------------------------ #
    # 文档入库
    # ------------------------------------------------------------------ #
    def add_documents(
        self,
        documents: list[Document],
        ids: list[str] | None = None,
    ) -> list[str]:
        """将文档批量写入向量库。

        Args:
            documents: 要入库的 Document 列表。
            ids: 自定义 ID 列表，为 ``None`` 时自动生成 UUID。

        Returns:
            list[str]: 实际写入的 ID 列表。
        """
        if not documents:
            return []

        doc_ids = ids or [str(uuid.uuid4()) for _ in documents]
        texts = [doc.page_content for doc in documents]
        metadatas = [_sanitize_metadata(doc.metadata) for doc in documents]

        if self._embedding is None:
            raise RuntimeError("Embedding 模型未成功初始化，无法执行文档入库。请检查模型配置或网络连接。")

        logger.info("正在生成 %d 条文档的 Embedding...", len(documents))
        embeddings = self._embedding.embed_documents(texts)

        self.collection.add(
            ids=doc_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info("成功入库 %d 条文档到集合 '%s'", len(documents), self.collection_name)
        return doc_ids

    # ------------------------------------------------------------------ #
    # 向量检索
    # ------------------------------------------------------------------ #
    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: dict[str, Any] | None = None,
    ) -> list[Document]:
        """向量相似度搜索。

        Args:
            query: 查询文本。
            top_k: 返回结果数量。
            filter_dict: ChromaDB where 过滤条件。

        Returns:
            list[Document]: 按相似度排序的文档列表。
        """
        if self._embedding is None:
            raise RuntimeError("Embedding 模型未成功初始化，无法执行向量检索。请检查模型配置或网络连接。")

        query_embedding = self._embedding.embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_dict,
            include=["documents", "metadatas", "distances"],
        )
        return _query_result_to_documents(results)

    # ------------------------------------------------------------------ #
    # 管理接口
    # ------------------------------------------------------------------ #
    def delete(self, ids: list[str]) -> None:
        """按 ID 删除文档。"""
        if ids:
            self.collection.delete(ids=ids)

    def clear(self) -> None:
        """清空当前集合。"""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name
        )

    def count(self) -> int:
        """返回集合中文档数量。"""
        return self.collection.count()

    def peek(self, limit: int = 5) -> list[Document]:
        """预览集合中的文档。"""
        results = self.collection.peek(limit=limit)
        return _query_result_to_documents(results)

    def get_by_filter(self, filter_dict: dict[str, Any]) -> list[Document]:
        """按 metadata 过滤条件查询文档。

        Args:
            filter_dict: ChromaDB ``where`` 过滤条件。

        Returns:
            list[Document]: 匹配的文档列表。
        """
        results = self.collection.get(where=filter_dict)
        return _query_result_to_documents(results)


# ------------------------------------------------------------------ #
# 工具函数
# ------------------------------------------------------------------ #


def _sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """将 metadata 清理为 ChromaDB 支持的类型（str / int / float / bool / list）。"""
    clean: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)):
            clean[k] = v
        elif isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v):
            # ChromaDB 不接受空列表，转换为空字符串
            clean[k] = v if v else ""
        elif v is None:
            clean[k] = ""
        else:
            # 其他类型转为字符串
            clean[k] = str(v)
    # ChromaDB 不接受空 metadata dict
    if not clean:
        clean["_source"] = "comedy_agent"
    return clean


def _query_result_to_documents(results: dict[str, Any]) -> list[Document]:
    """将 ChromaDB QueryResult / GetResult 转为 Document 列表。

    兼容 ``query()`` 返回的嵌套列表格式与 ``peek()`` 返回的扁平列表格式。
    """
    docs: list[Document] = []
    ids_list = results.get("ids", [])
    documents_list = results.get("documents", [])
    metadatas_list = results.get("metadatas", [])
    distances_list = results.get("distances", [])

    # 统一为嵌套列表格式
    def _normalize_list(data: Any) -> list[list[Any]]:
        if not data:
            return [[]]
        # peek/get 返回的是扁平列表，query 返回的是嵌套列表
        if isinstance(data[0], list):
            return data  # type: ignore[return-value]
        return [data]  # type: ignore[return-value]

    ids_nested = _normalize_list(ids_list)
    docs_nested = _normalize_list(documents_list)
    metas_nested = _normalize_list(metadatas_list)
    dists_nested = _normalize_list(distances_list)

    # 取第一层（query_embeddings 只传了一个）
    ids = ids_nested[0] if ids_nested else []
    texts = docs_nested[0] if docs_nested else []
    metas = metas_nested[0] if metas_nested else []
    distances = dists_nested[0] if dists_nested else []

    for i in range(len(ids)):
        meta = dict(metas[i]) if i < len(metas) and metas[i] is not None else {}
        meta["doc_id"] = ids[i]
        if i < len(distances) and distances[i] is not None:
            meta["distance"] = float(distances[i])
        text = texts[i] if i < len(texts) else ""
        docs.append(Document(page_content=text, metadata=meta))
    return docs
