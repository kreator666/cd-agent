"""知识系统统一检索接口。

整合多路召回：
1. 向量检索（TheoryStore / comedy_theory 集合）
2. 关键词检索（基于 knowledge_items.jsonl 的轻量倒排）
3. 元数据过滤（按 category）

结果使用 RRF（Reciprocal Rank Fusion）融合排序。
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from comedy_agent.core.knowledge_models import KnowledgeItem
from comedy_agent.rag.theory_store import TheoryStore

logger = logging.getLogger(__name__)

DEFAULT_RRF_K = 60
DEFAULT_VECTOR_TOP_K = 10
DEFAULT_KEYWORD_TOP_K = 10
DEFAULT_CORPUS_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "knowledge_items.jsonl"


# ------------------------------------------------------------------ #
# 轻量分词
# ------------------------------------------------------------------ #
_RE_EN_WORD = re.compile(r"[a-zA-Z0-9]+(?:[._\-][a-zA-Z0-9]+)*")
_RE_ZH_CHAR = re.compile(r"[\u4e00-\u9fa5]")


def _tokenize(text: str) -> set[str]:
    """对查询/文档做轻量分词，返回不重复 token 集合。"""
    tokens: set[str] = set()
    for m in _RE_EN_WORD.finditer(text):
        tokens.add(m.group().lower())
    for ch in _RE_ZH_CHAR.findall(text):
        tokens.add(ch)
    return tokens


# ------------------------------------------------------------------ #
# 关键词检索
# ------------------------------------------------------------------ #


@lru_cache(maxsize=1)
def _load_keyword_index(corpus_path: Path | None = None) -> list[KnowledgeItem]:
    """加载知识条目作为关键词检索索引（带缓存）。"""
    path = corpus_path or DEFAULT_CORPUS_PATH
    if not path.exists():
        logger.warning("关键词检索索引不存在: %s", path)
        return []

    items: list[KnowledgeItem] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(KnowledgeItem(**json.loads(line)))
            except Exception as e:
                logger.warning("解析知识条目失败: %s", e)
    logger.debug("关键词检索索引加载完成: %d 条", len(items))
    return items


def _keyword_search(
    query: str,
    items: list[KnowledgeItem],
    category: str | None = None,
    top_k: int = DEFAULT_KEYWORD_TOP_K,
) -> list[tuple[str, float]]:
    """基于 token 重叠的关键词检索。

    返回 (item_id, score) 列表，按得分降序。
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    candidates: list[tuple[str, float]] = []
    for item in items:
        if category and item.category != category:
            continue
        text = item.build_embedding_text()
        item_tokens = _tokenize(text)
        if not item_tokens:
            continue
        overlap = len(query_tokens & item_tokens)
        # 归一化：考虑查询 token 覆盖比例和文档长度惩罚
        score = overlap / max(len(query_tokens), 1)
        if score > 0:
            candidates.append((item.id, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:top_k]


# ------------------------------------------------------------------ #
# RRF 融合
# ------------------------------------------------------------------ #


def _rrf_fuse(
    vector_results: list[KnowledgeItem],
    keyword_results: list[tuple[str, float]],
    keyword_item_by_id: dict[str, KnowledgeItem],
    k: int = DEFAULT_RRF_K,
) -> list[tuple[float, str, KnowledgeItem | None]]:
    """对向量检索和关键词检索结果做 RRF 融合。

    Args:
        vector_results: 向量检索返回的 KnowledgeItem 列表（已按相似度排序）。
        keyword_results: 关键词检索返回的 (item_id, score) 列表（已按 score 排序）。
        keyword_item_by_id: 关键词索引中 id -> KnowledgeItem 的映射，用于还原只出现在关键词路径中的条目。
        k: RRF 常数，默认 60。

    Returns:
        按 RRF 分数降序排列的 (score, item_id, KnowledgeItem|None) 列表。
    """
    item_by_id: dict[str, KnowledgeItem] = {item.id: item for item in vector_results}
    item_by_id.update(keyword_item_by_id)
    scores: dict[str, float] = {}

    for rank, item in enumerate(vector_results, start=1):
        scores[item.id] = scores.get(item.id, 0.0) + 1.0 / (k + rank)

    for rank, (item_id, _) in enumerate(keyword_results, start=1):
        scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)

    fused = sorted(
        ((score, item_id, item_by_id.get(item_id)) for item_id, score in scores.items()),
        key=lambda x: x[0],
        reverse=True,
    )
    return fused


# ------------------------------------------------------------------ #
# 公共接口
# ------------------------------------------------------------------ #


class KnowledgeSystem:
    """知识系统统一入口。

    封装向量检索、关键词检索与 RRF 融合，供 Planner / Writer 调用。
    """

    def __init__(
        self,
        theory_store: TheoryStore | None = None,
        keyword_corpus_path: Path | None = None,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        """初始化知识系统。

        Args:
            theory_store: 理论知识向量库；为 None 时使用默认集合。
            keyword_corpus_path: 关键词检索用的 JSONL 路径；为 None 时使用默认路径。
            rrf_k: RRF 融合常数。
        """
        self.theory_store = theory_store or TheoryStore()
        self.keyword_corpus_path = keyword_corpus_path or DEFAULT_CORPUS_PATH
        self.rrf_k = rrf_k

    def retrieve(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 5,
        vector_top_k: int = DEFAULT_VECTOR_TOP_K,
        keyword_top_k: int = DEFAULT_KEYWORD_TOP_K,
    ) -> list[KnowledgeItem]:
        """检索与查询相关的理论知识。

        Args:
            query: 查询文本，通常是话题、段落目标或技法名。
            category: 按类别过滤（concept / technique / pattern / rule）。
            top_k: 最终返回结果数量。
            vector_top_k: 向量检索召回数量。
            keyword_top_k: 关键词检索召回数量。

        Returns:
            按融合分数排序的 KnowledgeItem 列表。
        """
        # 1. 向量检索
        vector_items: list[KnowledgeItem] = []
        try:
            vector_items = self.theory_store.search(
                query,
                category=category,
                top_k=vector_top_k,
            )
        except Exception as e:
            logger.warning("向量检索失败，仅使用关键词检索: %s", e)

        # 2. 关键词检索
        keyword_items = _load_keyword_index(self.keyword_corpus_path)
        keyword_item_by_id = {item.id: item for item in keyword_items}
        keyword_scores = _keyword_search(
            query,
            keyword_items,
            category=category,
            top_k=keyword_top_k,
        )

        # 3. RRF 融合
        fused = _rrf_fuse(vector_items, keyword_scores, keyword_item_by_id, k=self.rrf_k)

        # 4. 过滤掉只出现在 keyword 中但无法还原完整 KnowledgeItem 的结果
        results = [item for _, _, item in fused if item is not None][:top_k]
        logger.info(
            "知识检索完成: query='%s' category=%s vector=%d keyword=%d final=%d",
            query,
            category,
            len(vector_items),
            len(keyword_scores),
            len(results),
        )
        return results


def retrieve_knowledge(
    query: str,
    category: str | None = None,
    top_k: int = 5,
    vector_top_k: int = DEFAULT_VECTOR_TOP_K,
    keyword_top_k: int = DEFAULT_KEYWORD_TOP_K,
    theory_store: TheoryStore | None = None,
    keyword_corpus_path: Path | None = None,
) -> list[KnowledgeItem]:
    """模块级便捷函数：使用默认 KnowledgeSystem 检索知识。"""
    system = KnowledgeSystem(
        theory_store=theory_store,
        keyword_corpus_path=keyword_corpus_path,
    )
    return system.retrieve(
        query,
        category=category,
        top_k=top_k,
        vector_top_k=vector_top_k,
        keyword_top_k=keyword_top_k,
    )
