"""上下文注入机制 —— 检索结果自动拼接进 System Prompt / User Context。

控制 Token 预算，支持多种注入格式（列表、引用、摘要）。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.documents import Document

from comedy_agent.rag.retriever import ComedyRetriever

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Token 估算（轻量级，不依赖 tiktoken）
# ------------------------------------------------------------------ #


def _estimate_tokens(text: str) -> int:
    """粗略估算文本的 Token 数。

    中文按 ~1.5 tokens/字，英文按 ~0.25 tokens/字符，取保守值。
    """
    zh_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other_chars = len(text) - zh_chars
    return int(zh_chars * 1.5 + other_chars * 0.25 + 0.5)


# ------------------------------------------------------------------ #
# ContextInjector
# ------------------------------------------------------------------ #


class ContextInjector:
    """RAG 上下文注入器。

    根据用户查询检索相关知识，格式化为上下文文本，并控制 Token 预算。
    """

    def __init__(
        self,
        retriever: ComedyRetriever,
        max_context_tokens: int = 2000,
        format_style: str = "reference",
    ) -> None:
        """初始化上下文注入器。

        Args:
            retriever: 已初始化的混合检索器。
            max_context_tokens: 上下文最大 Token 预算。
            format_style: 注入格式，可选 ``reference`` / ``list`` / ``summary``。
        """
        self.retriever = retriever
        self.max_context_tokens = max_context_tokens
        self.format_style = format_style

    # ------------------------------------------------------------------ #
    # 核心接口
    # ------------------------------------------------------------------ #
    def inject(
        self,
        query: str,
        top_k: int = 5,
        system_prompt: str | None = None,
        memory_context: str | None = None,
    ) -> dict[str, str]:
        """检索相关知识并格式化为上下文。

        Args:
            query: 用户查询。
            top_k: 检索结果数量。
            system_prompt: 现有系统提示词，注入后会追加知识上下文说明。
            memory_context: 可选的用户记忆上下文文本，优先注入到 system prompt。

        Returns:
            dict: 包含 ``system_prompt``（更新后的系统提示）和 ``context``（上下文文本）的字典。
                若 ``system_prompt`` 为 ``None``，则上下文放在 ``context`` 中供外部拼接。
        """
        docs = self.retriever.retrieve(query, top_k=top_k)
        has_knowledge = bool(docs)

        if not has_knowledge and not memory_context:
            logger.debug("未检索到与 '%s' 相关的知识，且无记忆上下文", query)
            return {
                "system_prompt": system_prompt or "",
                "context": "",
            }

        context_text = ""
        if has_knowledge:
            context_text = self._format_context(docs, query)
            context_text = self._truncate_to_budget(context_text)

        if system_prompt:
            parts: list[str] = [system_prompt]

            if memory_context:
                parts.append(
                    f"【关于用户】\n"
                    f"以下是该用户的历史偏好与创作习惯，请在回答时参考：\n\n"
                    f"{memory_context}\n"
                    f"【关于用户结束】"
                )

            if context_text:
                parts.append(
                    f"【知识库参考】\n"
                    f"以下是与用户问题相关的喜剧行业知识，请在回答时参考：\n\n"
                    f"{context_text}\n"
                    f"【知识库参考结束】"
                )

            return {
                "system_prompt": "\n\n".join(parts),
                "context": context_text,
            }

        return {
            "system_prompt": "",
            "context": context_text,
        }

    # ------------------------------------------------------------------ #
    # 格式化
    # ------------------------------------------------------------------ #
    def _format_context(self, docs: list[Document], query: str) -> str:
        """按指定风格格式化检索结果。"""
        if self.format_style == "reference":
            return self._format_reference(docs)
        if self.format_style == "list":
            return self._format_list(docs)
        if self.format_style == "summary":
            return self._format_summary(docs)
        return self._format_reference(docs)

    @staticmethod
    def _format_reference(docs: list[Document]) -> str:
        """引用格式：带来源标注的编号列表。"""
        lines: list[str] = []
        for idx, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "未知来源")
            text = doc.page_content.strip().replace("\n", " ")
            lines.append(f"[{idx}] 来源: {source}\n{text}")
        return "\n\n".join(lines)

    @staticmethod
    def _format_list(docs: list[Document]) -> str:
        """列表格式：简洁的项目符号列表。"""
        lines: list[str] = []
        for doc in docs:
            text = doc.page_content.strip().replace("\n", " ")
            lines.append(f"- {text}")
        return "\n".join(lines)

    @staticmethod
    def _format_summary(docs: list[Document]) -> str:
        """摘要格式：合并为一段连续文本。"""
        texts = [doc.page_content.strip() for doc in docs]
        return "\n".join(texts)

    # ------------------------------------------------------------------ #
    # Token 预算控制
    # ------------------------------------------------------------------ #
    def _truncate_to_budget(self, text: str) -> str:
        """按 Token 预算截断文本，优先保留前面的结果。"""
        if _estimate_tokens(text) <= self.max_context_tokens:
            return text

        # 按段落/条目截断
        paragraphs = text.split("\n\n")
        truncated: list[str] = []
        current_len = 0
        budget = self.max_context_tokens

        for para in paragraphs:
            para_tokens = _estimate_tokens(para)
            if current_len + para_tokens > budget:
                if not truncated:
                    # 第一段就超出预算：强行截断第一段
                    para = self._truncate_text(para, budget)
                else:
                    # 已超出预算且已有内容，截断并添加提示
                    break
            truncated.append(para)
            current_len += _estimate_tokens(para)
            if current_len >= budget:
                break

        result = "\n\n".join(truncated)
        if len(truncated) < len(paragraphs) or _estimate_tokens(result) >= budget:
            result += "\n\n...（以下内容因 Token 预算限制已截断）"
        return result

    @staticmethod
    def _truncate_text(text: str, max_tokens: int) -> str:
        """对单段文本按字符数粗略截断。"""
        # 简单二分查找合适的截断位置
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if _estimate_tokens(text[:mid]) <= max_tokens:
                low = mid
            else:
                high = mid - 1
        return text[:low]

    # ------------------------------------------------------------------ #
    # 高级接口：与 LangChain Agent 集成
    # ------------------------------------------------------------------ #
    def build_messages(
        self,
        query: str,
        system_prompt: str | None = None,
        chat_history: list[tuple[str, str]] | None = None,
        top_k: int = 5,
        memory_context: str | None = None,
    ) -> list[tuple[str, str]]:
        """构建包含知识上下文的完整消息列表，供 LangChain Agent 使用。

        Args:
            query: 用户查询。
            system_prompt: 系统提示词。
            chat_history: 历史消息列表 [(role, content), ...]。
            top_k: 检索结果数量。
            memory_context: 可选的用户记忆上下文文本。

        Returns:
            list[tuple[str, str]]: 完整消息列表，可直接传给 Agent。
        """
        injected = self.inject(
            query, top_k=top_k, system_prompt=system_prompt, memory_context=memory_context
        )
        messages: list[tuple[str, str]] = []

        if injected["system_prompt"]:
            messages.append(("system", injected["system_prompt"]))

        if chat_history:
            messages.extend(chat_history)

        # 将上下文作为用户消息的一部分注入（如果未注入 system prompt）
        context = injected["context"]
        if context and not injected["system_prompt"]:
            user_msg = f"【参考知识】\n{context}\n\n【用户问题】\n{query}"
        else:
            user_msg = query

        messages.append(("human", user_msg))
        return messages
