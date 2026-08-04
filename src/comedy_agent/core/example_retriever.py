"""示例检索器 —— 从向量库中检索与当前创作目标相关的 Few-shot 示例。

Phase 4 数据增强：主题（60%）+ 风格（30%）+ 结构（10%）三维加权召回，
为 Writer 提供动态 Few-shot 示例。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.documents import Document

from comedy_agent.core.annotation import AnnotatedExample
from comedy_agent.core.config import settings
from comedy_agent.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "comedy_knowledge"
USER_COLLECTION_PREFIX = "user_knowledge_"

# 三维权重：主题 / 风格 / 结构
_WEIGHT_TOPIC = 0.6
_WEIGHT_STYLE = 0.3
_WEIGHT_STRUCTURE = 0.1


def _get_vector_stores(user_id: str | None = None) -> list[VectorStore]:
    """获取默认库与用户个人库（如有）。"""
    stores: list[VectorStore] = []
    stores.append(VectorStore(collection_name=DEFAULT_COLLECTION))
    if user_id:
        stores.append(VectorStore(collection_name=f"{USER_COLLECTION_PREFIX}{user_id}"))
    return stores


def _document_to_example(doc: Document) -> AnnotatedExample:
    """将 Document 转换为 AnnotatedExample。"""
    meta = doc.metadata or {}
    content = meta.get("content") or doc.page_content
    try:
        # 如果 metadata 里保存了完整 JSON，优先解析
        if "annotation" in meta and isinstance(meta["annotation"], str):
            data = json.loads(meta["annotation"])
            data.setdefault("embedding_text", doc.page_content)
            return AnnotatedExample(**data)
    except Exception:
        pass

    return AnnotatedExample(
        example_id=meta.get("doc_id", ""),
        content=content,
        setup=meta.get("setup", ""),
        punchline=meta.get("punchline", ""),
        callback=bool(meta.get("callback", False)),
        callback_to=meta.get("callback_to") or None,
        tags=meta.get("tags", []),
        topic=meta.get("topic", ""),
        style=meta.get("style", ""),
        kind=meta.get("kind", "standup"),
        structure_type=meta.get("structure_type", "script"),
        humor_score=float(meta.get("humor_score", 5)),
        setup_quality=float(meta.get("setup_quality", 5)),
        punchline_quality=float(meta.get("punchline_quality", 5)),
        pacing=float(meta.get("pacing", 5)),
        colloquial_score=float(meta.get("colloquial_score", 5)),
        resonance=float(meta.get("resonance", 5)),
        surprise=float(meta.get("surprise", 5)),
        observation=float(meta.get("observation", 5)),
        structure_integrity=float(meta.get("structure_integrity", 5)),
        performance_readiness=float(meta.get("performance_readiness", 5)),
        source=meta.get("source", ""),
        embedding_text=doc.page_content,
    )


def _compute_score(
    doc: Document,
    target_style: str | None,
    target_structure: str | None,
) -> float:
    """计算单条文档的三维加权分数。"""
    meta = doc.metadata or {}
    distance = meta.get("distance")
    if isinstance(distance, (int, float)):
        topic_score = max(0.0, 1.0 - float(distance))
    else:
        topic_score = 0.5

    # 风格匹配：完全匹配 1.0，否则 0.0；未指定时中性 0.5
    style_score = 0.5
    if target_style:
        doc_style = str(meta.get("style", "")).strip()
        style_score = 1.0 if doc_style == target_style else 0.0

    # 结构匹配
    structure_score = 0.5
    if target_structure:
        doc_structure = str(meta.get("structure_type", "")).strip()
        structure_score = 1.0 if doc_structure == target_structure else 0.0

    # 幽默分小加成：0 ~ 0.05
    humor = float(meta.get("humor_score", 5))
    humor_bonus = (humor - 5) / 100.0

    score = (
        _WEIGHT_TOPIC * topic_score
        + _WEIGHT_STYLE * style_score
        + _WEIGHT_STRUCTURE * structure_score
        + humor_bonus
    )
    return score


def retrieve_examples(
    query: str,
    top_k: int = 5,
    kind: str | None = "standup",
    style: str | None = None,
    structure_type: str | None = None,
    user_id: str | None = None,
    vector_stores: list[VectorStore] | None = None,
    filter_dict: dict[str, Any] | None = None,
) -> list[AnnotatedExample]:
    """检索与当前创作目标最相关的 Few-shot 示例。

    Args:
        query: 查询文本，通常是 section_goal 或 user_input。
        top_k: 返回示例数量。
        kind: 喜剧种类过滤，如 standup。
        style: 风格过滤/加权，如自嘲/观察。
        structure_type: 结构类型过滤/加权，如 script/story。
        user_id: 用户 ID，用于同时检索用户个人库。
        vector_stores: 可选的外部 VectorStore 列表（测试用）。
        filter_dict: 额外的 ChromaDB where 过滤条件。

    Returns:
        按相关性排序的 AnnotatedExample 列表。
    """
    if vector_stores is None:
        vector_stores = _get_vector_stores(user_id)

    # 构造过滤条件
    where: dict[str, Any] = {}
    if filter_dict:
        where.update(filter_dict)
    if kind:
        where["kind"] = kind

    # 同时召回多一点，便于重排
    recall_k = max(top_k * 3, 10)

    candidates: list[tuple[float, Document]] = []
    seen_ids: set[str] = set()

    for store in vector_stores:
        try:
            docs = store.search(query, top_k=recall_k, filter_dict=where if where else None)
        except Exception as e:
            logger.warning("向量库 %s 检索失败: %s", store.collection_name, e)
            continue

        for doc in docs:
            doc_id = doc.metadata.get("doc_id") if doc.metadata else None
            if doc_id and doc_id in seen_ids:
                continue
            if doc_id:
                seen_ids.add(doc_id)
            score = _compute_score(doc, style, structure_type)
            candidates.append((score, doc))

    # 按加权分数排序
    candidates.sort(key=lambda x: x[0], reverse=True)

    examples = [_document_to_example(doc) for _, doc in candidates[:top_k]]
    logger.info("检索到 %d 条示例，返回 Top-%d", len(candidates), len(examples))
    return examples


def ingest_annotations(
    annotations: list[AnnotatedExample],
    user_id: str | None = None,
    collection_name: str | None = None,
) -> list[str]:
    """将标注示例写入向量库。

    Args:
        annotations: 标注示例列表。
        user_id: 用户 ID，为 None 时写入默认库。
        collection_name: 自定义集合名称，为 None 时按 user_id 推断。

    Returns:
        写入的文档 ID 列表。
    """
    from langchain_core.documents import Document

    if collection_name is None:
        collection_name = (
            f"{USER_COLLECTION_PREFIX}{user_id}" if user_id else DEFAULT_COLLECTION
        )

    store = VectorStore(collection_name=collection_name)
    documents: list[Document] = []
    ids: list[str] = []
    for ex in annotations:
        meta = ex.model_dump()
        # 避免把长文本重复存进 metadata；embedding_text 作为 page_content
        meta.pop("embedding_text", None)
        meta.pop("content", None)
        meta["content"] = ex.content
        documents.append(Document(page_content=ex.embedding_text, metadata=meta))
        ids.append(ex.example_id)

    return store.add_documents(documents, ids=ids)
