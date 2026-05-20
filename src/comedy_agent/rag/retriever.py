"""混合检索实现 —— 向量检索 + BM25 + Cross-Encoder 重排序。

整合三种检索方式的优势：
- 向量检索：语义相似度高，擅长同义/近义查询
- BM25：关键词匹配精准，擅长专有名词/术语查询
- Cross-Encoder：精细重排序，提升 Top-K 质量
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from langchain_core.documents import Document

from comedy_agent.core.cache import Cache
from comedy_agent.core.observability import get_metrics, get_tracer
from comedy_agent.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# 可选依赖（多向量存储）
# ------------------------------------------------------------------ #
try:
    from comedy_agent.rag.comedy_optimizer import MultiVectorStore

    _HAS_MULTI_VECTOR = True
except ImportError:  # pragma: no cover
    _HAS_MULTI_VECTOR = False

# ------------------------------------------------------------------ #
# 可选依赖
# ------------------------------------------------------------------ #
try:
    from rank_bm25 import BM25Okapi

    _HAS_BM25 = True
except ImportError:  # pragma: no cover
    _HAS_BM25 = False
    logger.warning("rank-bm25 未安装，BM25 检索不可用")

try:
    from sentence_transformers import CrossEncoder

    _HAS_CROSS_ENCODER = True
except ImportError:  # pragma: no cover
    _HAS_CROSS_ENCODER = False
    logger.warning("sentence-transformers 未安装，Cross-Encoder 重排序不可用")


# ------------------------------------------------------------------ #
# 简单中文分词（无 jieba 依赖）
# ------------------------------------------------------------------ #

_RE_EN_WORD = re.compile(r"[a-zA-Z0-9]+(?:[._\-][a-zA-Z0-9]+)*")
_RE_ZH_CHAR = re.compile(r"[\u4e00-\u9fa5]")


def _simple_tokenize(text: str) -> list[str]:
    """轻量级分词：英文单词 + 中文字符。"""
    tokens: list[str] = []
    for m in _RE_EN_WORD.finditer(text):
        tokens.append(m.group().lower())
    for ch in _RE_ZH_CHAR.findall(text):
        tokens.append(ch)
    return tokens


# ------------------------------------------------------------------ #
# ComedyRetriever
# ------------------------------------------------------------------ #


class ComedyRetriever:
    """喜剧知识库混合检索器。

    召回阶段：向量检索 + BM25 关键词检索，合并去重。
    排序阶段：Cross-Encoder 精细重排序。
    """

    def __init__(
        self,
        vector_store: VectorStore,
        cross_encoder_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        multi_vector_store: "MultiVectorStore" | None = None,
        cache: Cache | None = None,
        cache_ttl: int = 300,
    ) -> None:
        """初始化混合检索器。

        Args:
            vector_store: 已初始化的向量存储实例。
            cross_encoder_name: Cross-Encoder 模型名称，用于重排序。
            multi_vector_store: 可选的多向量存储实例，启用后检索时会
                同时从多向量空间中召回结果并合并。
            cache: 可选的缓存实例，用于缓存检索结果。
            cache_ttl: 缓存过期时间（秒）。
        """
        self.vector_store = vector_store
        self.cross_encoder_name = cross_encoder_name
        self.multi_vector_store = multi_vector_store
        self.cache = cache
        self.cache_ttl = cache_ttl

        self._bm25: BM25Okapi | None = None
        self._corpus: list[Document] = []
        self._cross_encoder: Any | None = None

    # ------------------------------------------------------------------ #
    # 数据摄入
    # ------------------------------------------------------------------ #
    def ingest(self, documents: list[Document]) -> None:
        """将文档批量入库并建立 BM25 索引。

        Args:
            documents: 要入库的文档列表。
        """
        if not documents:
            return

        # 1. 向量库入库
        self.vector_store.add_documents(documents)

        # 1.5 多向量库入库（如果启用）
        if self.multi_vector_store is not None:
            self.multi_vector_store.add_documents(documents)
            logger.info("多向量库已入库 %d 条文档", len(documents))

        # 2. 更新 BM25 索引
        if _HAS_BM25:
            self._corpus.extend(documents)
            tokenized = [_simple_tokenize(d.page_content) for d in self._corpus]
            self._bm25 = BM25Okapi(tokenized)
            logger.info("BM25 索引已更新，共 %d 条文档", len(self._corpus))
        else:
            logger.warning("rank-bm25 未安装，跳过 BM25 索引构建")

    # ------------------------------------------------------------------ #
    # 混合检索
    # ------------------------------------------------------------------ #
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        vector_top_k: int | None = None,
        bm25_top_k: int | None = None,
        use_cache: bool = True,
    ) -> list[Document]:
        """执行混合检索并返回重排序后的结果。

        Args:
            query: 用户查询。
            top_k: 最终返回结果数量。
            vector_top_k: 向量检索召回数量，为 ``None`` 时取 ``top_k * 2``。
            bm25_top_k: BM25 检索召回数量，为 ``None`` 时取 ``top_k * 2``。
            use_cache: 是否使用缓存。

        Returns:
            list[Document]: 按相关性排序的文档列表。
        """
        tracer = get_tracer()
        metrics = get_metrics()

        with tracer.span(
            "retriever.retrieve",
            input_data={"query": query[:200], "top_k": top_k},
            metadata={"use_cache": use_cache},
        ) as span:
            # 尝试读取缓存
            cache_key = None
            if use_cache and self.cache is not None:
                cache_key = self._make_cache_key(query, top_k, vector_top_k, bm25_top_k)
                cached = self.cache.get_json(cache_key)
                if cached is not None:
                    logger.debug("缓存命中: %s", cache_key)
                    docs = [Document(page_content=d["content"], metadata=d["metadata"]) for d in cached]
                    metrics.record("retriever.cache_hit", 1)
                    metrics.record("retriever.results", len(docs))
                    span.output_data = {"cache_hit": True, "results": len(docs)}
                    return docs

            vec_k = vector_top_k or top_k * 2
            bm25_k = bm25_top_k or top_k * 2

            # 1. 向量检索召回
            vec_results = self.vector_store.search(query, top_k=vec_k)
            logger.debug("向量召回 %d 条", len(vec_results))
            metrics.record("retriever.vector_results", len(vec_results))

            # 1.5 多向量检索召回（如果启用）
            if self.multi_vector_store is not None:
                mv_results = self.multi_vector_store.search(
                    query, top_k=vec_k, return_original=True
                )
                logger.debug("多向量召回 %d 条", len(mv_results))
                vec_results = self._merge_results(vec_results, mv_results)

            # 2. BM25 召回
            bm25_results: list[Document] = []
            if self._bm25 is not None:
                bm25_results = self._bm25_search(query, top_k=bm25_k)
                logger.debug("BM25 召回 %d 条", len(bm25_results))
                metrics.record("retriever.bm25_results", len(bm25_results))

            # 3. 合并去重（按 doc_id 或 content）
            merged = self._merge_results(vec_results, bm25_results)
            logger.debug("合并去重后 %d 条", len(merged))

            if not merged:
                span.output_data = {"results": 0}
                return []

            # 4. Cross-Encoder 重排序
            reranked = self._rerank(query, merged, top_k=top_k)
            logger.debug("重排序后返回 %d 条", len(reranked))

            # 写入缓存
            if use_cache and self.cache is not None and cache_key is not None:
                serializable = [
                    {"content": d.page_content, "metadata": d.metadata}
                    for d in reranked
                ]
                self.cache.set_json(cache_key, serializable, ttl=self.cache_ttl)

            metrics.record("retriever.results", len(reranked))
            metrics.record("retriever.duration_ms", span.duration_ms)
            span.output_data = {"results": len(reranked)}
            return reranked

    @staticmethod
    def _make_cache_key(query: str, top_k: int, vector_top_k: int | None, bm25_top_k: int | None) -> str:
        """生成检索缓存键。"""
        raw = f"retrieve:{query}:{top_k}:{vector_top_k}:{bm25_top_k}"
        return "rag:" + hashlib.md5(raw.encode()).hexdigest()

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #
    def _bm25_search(self, query: str, top_k: int) -> list[Document]:
        """BM25 关键词检索。"""
        if self._bm25 is None or not self._corpus:
            return []

        query_tokens = _simple_tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        # 取 top_k
        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]

        results: list[Document] = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            doc = self._corpus[idx]
            meta = {**doc.metadata, "bm25_score": float(scores[idx])}
            results.append(Document(page_content=doc.page_content, metadata=meta))
        return results

    @staticmethod
    def _merge_results(
        vec_results: list[Document],
        bm25_results: list[Document],
    ) -> list[Document]:
        """合并向量与 BM25 结果，按 doc_id / content 去重。"""
        seen: set[str] = set()
        merged: list[Document] = []

        for doc in vec_results + bm25_results:
            key = doc.metadata.get("doc_id") or doc.page_content
            if key not in seen:
                seen.add(key)
                merged.append(doc)
        return merged

    def _rerank(
        self,
        query: str,
        documents: list[Document],
        top_k: int,
    ) -> list[Document]:
        """Cross-Encoder 重排序。"""
        if not _HAS_CROSS_ENCODER:
            logger.warning("sentence-transformers 未安装，跳过重排序")
            return documents[:top_k]

        if self._cross_encoder is None:
            logger.info("加载 Cross-Encoder: %s", self.cross_encoder_name)
            self._cross_encoder = CrossEncoder(self.cross_encoder_name)

        pairs = [(query, doc.page_content) for doc in documents]
        scores = self._cross_encoder.predict(pairs)

        # 按分数降序排序
        scored = list(zip(documents, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        result: list[Document] = []
        for doc, score in scored[:top_k]:
            meta = {**doc.metadata, "rerank_score": float(score)}
            result.append(Document(page_content=doc.page_content, metadata=meta))
        return result

    # ------------------------------------------------------------------ #
    # 管理接口
    # ------------------------------------------------------------------ #
    def clear(self) -> None:
        """清空向量库与 BM25 索引。"""
        self.vector_store.clear()
        self._corpus.clear()
        self._bm25 = None
        logger.info("ComedyRetriever 已清空")
