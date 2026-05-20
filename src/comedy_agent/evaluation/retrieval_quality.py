"""检索质量评估 —— 相关性指标计算（Recall / Precision / MRR / NDCG）。

支持对带标注的数据集计算标准 IR 指标，评估 RAG 检索效果。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document


@dataclass
class RetrievalResult:
    """单条查询的检索评估结果。"""

    query: str = ""
    recall_at_k: dict[int, float] = field(default_factory=dict)
    precision_at_k: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    ndcg_at_k: dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "recall_at_k": self.recall_at_k,
            "precision_at_k": self.precision_at_k,
            "mrr": self.mrr,
            "ndcg_at_k": self.ndcg_at_k,
        }


@dataclass
class RetrievalBatchResult:
    """批量检索评估结果。"""

    per_query: list[RetrievalResult] = field(default_factory=list)

    # 聚合统计
    avg_recall_at_k: dict[int, float] = field(default_factory=dict)
    avg_precision_at_k: dict[int, float] = field(default_factory=dict)
    avg_mrr: float = 0.0
    avg_ndcg_at_k: dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "avg_recall_at_k": self.avg_recall_at_k,
            "avg_precision_at_k": self.avg_precision_at_k,
            "avg_mrr": self.avg_mrr,
            "avg_ndcg_at_k": self.avg_ndcg_at_k,
            "per_query": [r.to_dict() for r in self.per_query],
        }


class RetrievalEvaluator:
    """检索质量评估器。

    计算标准信息检索指标，支持自定义 relevance 标注。
    """

    def __init__(self, k_values: tuple[int, ...] = (1, 3, 5, 10)) -> None:
        self.k_values = k_values

    # ------------------------------------------------------------------ #
    # 公共 API
    # ------------------------------------------------------------------ #
    def evaluate(
        self,
        query: str,
        retrieved: list[Document],
        relevant_doc_ids: set[str],
        relevance_scores: dict[str, float] | None = None,
    ) -> RetrievalResult:
        """评估单条查询的检索质量。

        Args:
            query: 查询文本。
            retrieved: 检索返回的文档列表（按相关性排序）。
            relevant_doc_ids: 相关文档 ID 集合。
            relevance_scores: 可选的文档 relevance 分数（用于 NDCG）。
                key 为 doc_id，value 为 [0, 1] 之间的分数。

        Returns:
            RetrievalResult: 包含各指标的结果。
        """
        result = RetrievalResult(query=query)

        retrieved_ids = [
            str(d.metadata.get("doc_id", d.page_content)) for d in retrieved
        ]

        for k in self.k_values:
            top_k = retrieved_ids[:k]
            result.recall_at_k[k] = self._recall_at_k(top_k, relevant_doc_ids)
            result.precision_at_k[k] = self._precision_at_k(top_k, relevant_doc_ids)
            result.ndcg_at_k[k] = self._ndcg_at_k(
                top_k, relevant_doc_ids, relevance_scores or {}
            )

        result.mrr = self._mrr(retrieved_ids, relevant_doc_ids)
        return result

    def evaluate_batch(
        self,
        queries: list[str],
        all_retrieved: list[list[Document]],
        all_relevant: list[set[str]],
        all_relevance_scores: list[dict[str, float] | None] | None = None,
    ) -> RetrievalBatchResult:
        """批量评估检索质量。

        Args:
            queries: 查询列表。
            all_retrieved: 每个查询对应的检索结果。
            all_relevant: 每个查询对应的相关文档 ID 集合。
            all_relevance_scores: 可选的每查询 relevance 分数。

        Returns:
            RetrievalBatchResult: 聚合结果。
        """
        per_query: list[RetrievalResult] = []
        rel_scores = all_relevance_scores or [None] * len(queries)

        for q, ret, rel, scores in zip(queries, all_retrieved, all_relevant, rel_scores):
            per_query.append(self.evaluate(q, ret, rel, scores))

        batch = RetrievalBatchResult(per_query=per_query)

        # 聚合平均
        n = len(per_query)
        if n == 0:
            return batch

        for k in self.k_values:
            batch.avg_recall_at_k[k] = round(
                sum(r.recall_at_k.get(k, 0.0) for r in per_query) / n, 4
            )
            batch.avg_precision_at_k[k] = round(
                sum(r.precision_at_k.get(k, 0.0) for r in per_query) / n, 4
            )
            batch.avg_ndcg_at_k[k] = round(
                sum(r.ndcg_at_k.get(k, 0.0) for r in per_query) / n, 4
            )

        batch.avg_mrr = round(
            sum(r.mrr for r in per_query) / n, 4
        )

        return batch

    # ------------------------------------------------------------------ #
    # 静态指标方法
    # ------------------------------------------------------------------ #
    @staticmethod
    def _recall_at_k(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
        """Recall@K = 检索到的相关文档 / 所有相关文档。"""
        if not relevant_ids:
            return 0.0
        hits = len(set(retrieved_ids) & relevant_ids)
        return round(hits / len(relevant_ids), 4)

    @staticmethod
    def _precision_at_k(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
        """Precision@K = 检索到的相关文档 / K。"""
        if not retrieved_ids:
            return 0.0
        hits = len(set(retrieved_ids) & relevant_ids)
        return round(hits / len(retrieved_ids), 4)

    @staticmethod
    def _mrr(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
        """MRR = 第一个相关文档排名的倒数。"""
        for i, doc_id in enumerate(retrieved_ids, start=1):
            if doc_id in relevant_ids:
                return round(1.0 / i, 4)
        return 0.0

    @staticmethod
    def _ndcg_at_k(
        retrieved_ids: list[str],
        relevant_ids: set[str],
        relevance_scores: dict[str, float],
    ) -> float:
        """NDCG@K —— 归一化折损累积增益。"""
        if not retrieved_ids or not relevant_ids:
            return 0.0

        k = len(retrieved_ids)

        # DCG
        dcg = 0.0
        for i, doc_id in enumerate(retrieved_ids, start=1):
            rel = relevance_scores.get(doc_id, 1.0 if doc_id in relevant_ids else 0.0)
            dcg += rel / math.log2(i + 1)

        # Ideal DCG
        ideal_rels = sorted(
            [relevance_scores.get(did, 1.0) for did in relevant_ids],
            reverse=True,
        )[:k]
        idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal_rels))

        if idcg == 0:
            return 0.0
        return round(dcg / idcg, 4)
