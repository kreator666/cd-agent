"""统一记忆接口 —— UnifiedMemory。

对上层（Agent、Skill、API）提供单一入口，内部聚合短期/中期记忆，
并支持 Token 预算控制的上下文文本生成。
"""

from __future__ import annotations

import logging
from typing import Any

from comedy_agent.memory.medium_term import SQLMemoryStore
from comedy_agent.memory.models import (
    ConversationData,
    DocumentData,
    KnowledgeCardData,
    ScriptData,
    UserContext,
    UserProfileData,
)
from comedy_agent.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Token 估算（与 rag/context_injector.py 保持一致）
# ------------------------------------------------------------------ #


def _estimate_tokens(text: str) -> int:
    """粗略估算文本 Token 数。中文 ~1.5 tokens/字，英文 ~0.25 tokens/字符。"""
    zh_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other_chars = len(text) - zh_chars
    return int(zh_chars * 1.5 + other_chars * 0.25 + 0.5)


# ------------------------------------------------------------------ #
# UnifiedMemory
# ------------------------------------------------------------------ #


class UnifiedMemory(MemoryStore):
    """统一记忆接口。

    内部持有 ``SQLMemoryStore`` 实例，提供：
    1. 标准 MemoryStore 接口的直接透传；
    2. ``build_context_text()`` 方法，将用户记忆格式化为文本，
       支持 Token 预算控制，可直接拼接到 System Prompt。
    """

    def __init__(self, db_url: str | None = None) -> None:
        """初始化 UnifiedMemory。

        Args:
            db_url: 数据库连接 URL，默认使用配置文件中的路径。
        """
        self._store = SQLMemoryStore(db_url=db_url)
        logger.info("UnifiedMemory initialized")

    # ------------------------------------------------------------------ #
    # 透传接口（直接委托给 SQLMemoryStore）
    # ------------------------------------------------------------------ #
    def get_or_create_user(
        self, user_id: str, nickname: str | None = None
    ) -> UserProfileData:
        return self._store.get_or_create_user(user_id, nickname)

    def save_conversation(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        summary: str | None = None,
    ) -> None:
        self._store.save_conversation(user_id, session_id, messages, summary)

    def load_conversation(
        self, user_id: str, session_id: str
    ) -> ConversationData | None:
        return self._store.load_conversation(user_id, session_id)

    def list_conversations(
        self, user_id: str, limit: int = 10
    ) -> list[ConversationData]:
        return self._store.list_conversations(user_id, limit)

    def delete_conversation(self, user_id: str, session_id: str) -> bool:
        return self._store.delete_conversation(user_id, session_id)

    def save_script(self, user_id: str, script: ScriptData) -> ScriptData:
        return self._store.save_script(user_id, script)

    def load_script(self, script_id: str) -> ScriptData | None:
        return self._store.load_script(script_id)

    def list_scripts(
        self, user_id: str, script_type: str | None = None, min_rating: float | None = None
    ) -> list[ScriptData]:
        return self._store.list_scripts(user_id, script_type, min_rating)

    def list_all_scripts(
        self, min_rating: float | None = None
    ) -> list[ScriptData]:
        return self._store.list_all_scripts(min_rating)

    def delete_script(self, script_id: str) -> bool:
        return self._store.delete_script(script_id)

    def rate_script(self, script_id: str, rating: float) -> bool:
        return self._store.rate_script(script_id, rating)

    def build_user_context(
        self, user_id: str, max_conversations: int = 3
    ) -> UserContext:
        return self._store.build_user_context(user_id, max_conversations)

    # ------------------------------------------------------------------ #
    # 用户文档（知识库上传）
    # ------------------------------------------------------------------ #
    def save_document(self, document: DocumentData) -> DocumentData:
        return self._store.save_document(document)

    def list_documents(self, user_id: str) -> list[DocumentData]:
        return self._store.list_documents(user_id)

    def get_document(self, user_id: str, doc_id: str) -> DocumentData | None:
        return self._store.get_document(user_id, doc_id)

    def delete_document(self, user_id: str, doc_id: str) -> bool:
        return self._store.delete_document(user_id, doc_id)

    # ------------------------------------------------------------------ #
    # 知识卡片（技巧库）
    # ------------------------------------------------------------------ #
    def save_knowledge_card(self, card: KnowledgeCardData) -> KnowledgeCardData:
        return self._store.save_knowledge_card(card)

    def list_knowledge_cards(
        self, user_id: str, card_type: str | None = None, tag: str | None = None
    ) -> list[KnowledgeCardData]:
        return self._store.list_knowledge_cards(user_id, card_type=card_type, tag=tag)

    def get_knowledge_card(self, user_id: str, card_id: str) -> KnowledgeCardData | None:
        return self._store.get_knowledge_card(user_id, card_id)

    def delete_knowledge_card(self, user_id: str, card_id: str) -> bool:
        return self._store.delete_knowledge_card(user_id, card_id)

    # ------------------------------------------------------------------ #
    # 高级接口：Token 预算控制的上下文文本
    # ------------------------------------------------------------------ #
    def build_context_text(
        self,
        user_id: str,
        max_tokens: int = 800,
        include_recent_conversations: bool = True,
        include_recent_scripts: bool = True,
        max_conversations: int = 2,
        max_scripts: int = 2,
    ) -> str:
        """构建用户记忆上下文文本，用于注入 Agent System Prompt。

        按优先级组装：近期会话 > 近期作品，
        超出 Token 预算时从低优先级内容开始截断。

        Args:
            user_id: 用户唯一标识。
            max_tokens: 上下文最大 Token 预算。
            include_recent_conversations: 是否包含近期会话。
            include_recent_scripts: 是否包含近期作品。
            max_conversations: 最大会话数。
            max_scripts: 最大作品数。

        Returns:
            str: 格式化后的记忆上下文文本，若无可注入记忆则返回空字符串。
        """
        ctx = self.build_user_context(user_id, max_conversations=max_conversations)
        items: list[tuple[int, str]] = []  # (priority, text)

        # 1. 近期会话（逐条加入，支持段内截断）
        if include_recent_conversations and ctx.recent_conversations:
            conv_items = []
            for conv in ctx.recent_conversations[:max_conversations]:
                if conv.summary:
                    conv_items.append(f"- 会话 {conv.session_id}: {conv.summary}")
                else:
                    last_msg = conv.messages[-1] if conv.messages else {}
                    content = str(last_msg.get("content", ""))[:60]
                    conv_items.append(f"- 会话 {conv.session_id}: {content}...")
            if conv_items:
                items.append((2, "【近期会话摘要】\n" + "\n".join(conv_items)))

        # 3. 近期作品（逐条加入，支持段内截断）
        if include_recent_scripts and ctx.recent_scripts:
            script_items = []
            for sc in ctx.recent_scripts[:max_scripts]:
                info = sc.title or sc.script_id
                if sc.script_type:
                    info += f" ({sc.script_type})"
                if sc.rating is not None:
                    info += f" [评分: {sc.rating}]"
                script_items.append(f"- {info}")
            if script_items:
                items.append((3, "【近期作品】\n" + "\n".join(script_items)))

        # Token 预算控制：逐段处理，段内逐条截断
        result_parts: list[str] = []
        current_tokens = 0
        omitted = False

        for priority, part in items:
            part_tokens = _estimate_tokens(part)
            if current_tokens + part_tokens <= max_tokens:
                result_parts.append(part)
                current_tokens += part_tokens
                continue

            # 该段超预算，尝试段内逐条截断
            lines = part.split("\n")
            header = lines[0] if lines else ""
            header_tokens = _estimate_tokens(header)
            if current_tokens + header_tokens > max_tokens:
                # 连标题都放不下，直接省略整段
                omitted = True
                continue

            kept_lines = [header]
            current_tokens += header_tokens
            for line in lines[1:]:
                line_tokens = _estimate_tokens(line)
                if current_tokens + line_tokens > max_tokens:
                    omitted = True
                    break
                kept_lines.append(line)
                current_tokens += line_tokens

            if len(kept_lines) > 1:
                result_parts.append("\n".join(kept_lines))
            else:
                omitted = True

        result = "\n\n".join(result_parts)
        if omitted:
            result += "\n\n...（更多记忆因 Token 预算限制已省略）"
        return result


# ------------------------------------------------------------------ #
# 辅助：文本截断
# ------------------------------------------------------------------ #


def _truncate_text(text: str, max_tokens: int) -> str:
    """二分查找合适的截断位置。"""
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if _estimate_tokens(text[:mid]) <= max_tokens:
            low = mid
        else:
            high = mid - 1
    return text[:low]
