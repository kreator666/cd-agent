"""Skill 基类 —— 所有喜剧 Skill 的抽象接口。

预留接口，将在任务 1.4 / 2.1 / 2.2 中完善。
"""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.tools import BaseTool

from comedy_agent.rag.vector_store import VectorStore


class ComedySkill(BaseTool, ABC):
    """喜剧 Skill 抽象基类。

    每个 Skill 对应一种喜剧创作能力（脱口秀、相声、小品等），
    或辅助能力（笑点分析、剧本评估等）。
    """

    # 任务类型，用于模型分层配置
    # creative: 创意任务（创作类）
    # analytical: 分析任务（评估/分析类）
    # fast: 快速响应任务
    task_type: str = "creative"

    # 用户指定的覆盖模型，优先级高于 task_type 分层配置
    model_name: str | None = None

    # 可选的知识库检索器（默认知识库）
    retriever: Any | None = None

    # 用户个人知识库缓存
    _user_vector_stores: dict[str, VectorStore] = {}

    def _retrieve_knowledge(
        self,
        query: str,
        user_id: str | None = None,
        top_k: int = 5,
        kind: str | None = None,
        style: str | None = None,
    ) -> list[Any]:
        """检索默认知识库 + 用户个人知识库。

        Args:
            query: 检索查询（通常用 topic/theme）。
            user_id: 可选用户标识，用于检索个人知识库。
            top_k: 默认库召回数量。
            kind: 喜剧种类过滤，如 "standup" / "sketch" / "manzai"。
            style: 风格过滤，如 "traditional" / "modern" / "自嘲"。

        Returns:
            去重后的 Document 列表。
        """
        # 构建 ChromaDB filter
        filter_dict: dict[str, Any] | None = None
        if kind or style:
            filter_dict = {}
            if kind:
                filter_dict["kind"] = kind
            if style:
                filter_dict["style"] = style

        all_docs: list[Any] = []

        # 1. 用户个人知识库
        if user_id:
            try:
                store = self._get_user_vector_store(user_id)
                user_docs = store.search(query, top_k=3, filter_dict=filter_dict)
                all_docs.extend(user_docs)
            except Exception:
                pass

        # 2. 默认知识库
        if self.retriever is not None:
            try:
                default_docs = self.retriever.retrieve(query, top_k=top_k, filter_dict=filter_dict)
                all_docs.extend(default_docs)
            except Exception:
                pass

        # 去重
        seen: set[str] = set()
        unique_docs: list[Any] = []
        for doc in all_docs:
            key = doc.metadata.get("doc_id") or doc.page_content
            if key and key not in seen:
                seen.add(key)
                unique_docs.append(doc)
        return unique_docs[:6]

    def _get_user_vector_store(self, user_id: str) -> VectorStore:
        """获取或创建用户的个人知识库向量存储。"""
        if user_id not in self._user_vector_stores:
            from comedy_agent.core.config import settings

            self._user_vector_stores[user_id] = VectorStore(
                collection_name=f"user_knowledge_{user_id}",
                persist_path=str(settings.vector_db_path),
            )
        return self._user_vector_stores[user_id]

    @staticmethod
    def _format_knowledge(docs: list[Any]) -> str:
        """将检索结果格式化为 Prompt 文本。"""
        if not docs:
            return ""
        lines: list[str] = []
        for idx, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "未知来源")
            text = doc.page_content.strip().replace("\n", " ")
            lines.append(f"[{idx}] 来源: {source}\n{text}")
        knowledge_text = "\n\n".join(lines)
        return (
            f"【知识库参考】\n"
            f"以下是与本次创作相关的喜剧行业知识，请在创作时参考：\n\n"
            f"{knowledge_text}\n"
            f"【知识库参考结束】"
        )

    @abstractmethod
    def _run(self, *args: Any, **kwargs: Any) -> str:
        """同步执行 Skill。"""
        ...

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """异步执行 Skill（默认调用同步版本）。"""
        return self._run(*args, **kwargs)
