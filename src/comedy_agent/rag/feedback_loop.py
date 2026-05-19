"""高评分内容回流 —— 将用户优质创作自动解析、分块、增量入库。

让知识库持续吸收用户的高评分剧本，实现"越用越懂行"的进化效果。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.documents import Document

from comedy_agent.core.config import settings
from comedy_agent.memory.models import ScriptData
from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.rag.chunker import DocumentChunker
from comedy_agent.rag.retriever import ComedyRetriever
from comedy_agent.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# FeedbackLoop
# ------------------------------------------------------------------ #


class FeedbackLoop:
    """用户高评分剧本回流器。

    流水线：筛选高评分作品 → 解析为 Document → 智能分块 → 增量入库。
    """

    def __init__(
        self,
        memory: UnifiedMemory | None = None,
        retriever: ComedyRetriever | None = None,
        min_rating: float = 4.0,
    ) -> None:
        """初始化回流器。

        Args:
            memory: 统一记忆接口，为 ``None`` 时自动创建。
            retriever: 混合检索器，为 ``None`` 时自动创建。
            min_rating: 最低评分阈值，默认 4.0（满分 5.0）。
        """
        self.memory = memory or UnifiedMemory()
        self.min_rating = min_rating

        if retriever is None:
            vector_store = VectorStore(
                collection_name="comedy_knowledge",
                persist_path=str(settings.vector_db_path),
            )
            retriever = ComedyRetriever(vector_store=vector_store)
        self.retriever = retriever

    # ------------------------------------------------------------------ #
    # 主入口
    # ------------------------------------------------------------------ #
    def ingest_high_rated_scripts(
        self,
        user_id: str | None = None,
        chunk_strategy: str = "paragraph",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """将高评分剧本回流到知识库。

        Args:
            user_id: 指定用户标识，为 ``None`` 时处理所有用户。
            chunk_strategy: 分块策略，可选 ``fixed`` / ``paragraph`` / ``scene`` / ``dialogue``。
            dry_run: 为 ``True`` 时只统计不实际入库。

        Returns:
            dict: 回流统计信息。
        """
        scripts = self._fetch_scripts(user_id)
        logger.info("找到 %d 条符合条件的作品", len(scripts))

        ingested_scripts = 0
        total_chunks = 0
        script_ids: list[str] = []
        skipped: list[str] = []

        for script in scripts:
            # 去重：已入库则跳过
            if self._is_already_ingested(script.script_id):
                skipped.append(script.script_id)
                logger.debug("作品 %s 已入库，跳过", script.script_id)
                continue

            # 转为 Document
            doc = self._script_to_document(script)

            # 分块
            chunks = self._chunk_document(doc, strategy=chunk_strategy)
            if not chunks:
                logger.warning("作品 %s 分块后为空，跳过", script.script_id)
                continue

            # 入库
            if not dry_run:
                self.retriever.ingest(chunks)

            ingested_scripts += 1
            total_chunks += len(chunks)
            script_ids.append(script.script_id)
            logger.info("作品 %s 已回流（%d 块）", script.script_id, len(chunks))

        result = {
            "ingested_scripts": ingested_scripts,
            "total_chunks": total_chunks,
            "script_ids": script_ids,
            "skipped": skipped,
            "dry_run": dry_run,
        }
        logger.info("回流完成: %s", result)
        return result

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #
    def _fetch_scripts(self, user_id: str | None = None) -> list[ScriptData]:
        """获取高评分作品列表。"""
        if user_id:
            scripts = self.memory.list_scripts(user_id)
        else:
            scripts = self.memory.list_all_scripts(min_rating=self.min_rating)

        # 按评分过滤（list_scripts 不支持 min_rating）
        return [
            s
            for s in scripts
            if s.rating is not None and s.rating >= self.min_rating
        ]

    def _is_already_ingested(self, script_id: str) -> bool:
        """检查作品是否已入库（通过 source_script_id 查询向量库）。"""
        try:
            existing = self.retriever.vector_store.get_by_filter(
                {"source_script_id": script_id}
            )
            return len(existing) > 0
        except Exception as e:
            logger.warning("检查入库状态时出错: %s", e)
            return False

    @staticmethod
    def _script_to_document(script: ScriptData) -> Document:
        """将作品转为 Document 对象，注入丰富 metadata。"""
        meta: dict[str, Any] = {
            "source_script_id": script.script_id,
            "source": "user_feedback_loop",
            "script_type": script.script_type or "",
            "rating": script.rating if script.rating is not None else 0.0,
            "title": script.title or "",
            "feedback_loop": True,
        }
        if script.tags:
            meta["tags"] = script.tags

        # 在 content 开头注入标题，提升检索效果
        content = script.content
        if script.title:
            content = f"【{script.title}】\n\n{content}"

        return Document(page_content=content, metadata=meta)

    @staticmethod
    def _chunk_document(doc: Document, strategy: str = "paragraph") -> list[Document]:
        """对作品文档进行分块。"""
        if strategy == "fixed":
            return DocumentChunker.split_fixed([doc])
        return DocumentChunker.auto_split([doc], strategy=strategy)
