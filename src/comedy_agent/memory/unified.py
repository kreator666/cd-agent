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
    PreferenceItem,
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

    def save_preference(self, user_id: str, key: str, value: Any) -> None:
        self._store.save_preference(user_id, key, value)

    def load_preference(self, user_id: str, key: str) -> Any | None:
        return self._store.load_preference(user_id, key)

    def list_preferences(self, user_id: str) -> list[PreferenceItem]:
        return self._store.list_preferences(user_id)

    def save_script(self, user_id: str, script: ScriptData) -> ScriptData:
        return self._store.save_script(user_id, script)

    def load_script(self, script_id: str) -> ScriptData | None:
        return self._store.load_script(script_id)

    def list_scripts(
        self, user_id: str, script_type: str | None = None
    ) -> list[ScriptData]:
        return self._store.list_scripts(user_id, script_type)

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
    # 高级接口：Token 预算控制的上下文文本
    # ------------------------------------------------------------------ #
    def build_context_text(
        self,
        user_id: str,
        max_tokens: int = 800,
        include_preferences: bool = True,
        include_recent_conversations: bool = True,
        include_recent_scripts: bool = True,
        max_conversations: int = 2,
        max_scripts: int = 2,
    ) -> str:
        """构建用户记忆上下文文本，用于注入 Agent System Prompt。

        按优先级组装：偏好 > 近期会话 > 近期作品，
        超出 Token 预算时从低优先级内容开始截断。

        Args:
            user_id: 用户唯一标识。
            max_tokens: 上下文最大 Token 预算。
            include_preferences: 是否包含用户偏好。
            include_recent_conversations: 是否包含近期会话。
            include_recent_scripts: 是否包含近期作品。
            max_conversations: 最大会话数。
            max_scripts: 最大作品数。

        Returns:
            str: 格式化后的记忆上下文文本，若无可注入记忆则返回空字符串。
        """
        parts: list[str] = []
        ctx = self.build_user_context(user_id, max_conversations=max_conversations)

        # 1. 用户偏好（最高优先级）
        if include_preferences and ctx.preferences:
            pref_lines = [f"- {p.key}: {p.value}" for p in ctx.preferences]
            parts.append("【用户偏好】\n" + "\n".join(pref_lines))

        # 2. 近期会话
        if include_recent_conversations and ctx.recent_conversations:
            conv_lines = []
            for conv in ctx.recent_conversations[:max_conversations]:
                if conv.summary:
                    conv_lines.append(f"- 会话 {conv.session_id}: {conv.summary}")
                else:
                    # 取最后一条消息作为摘要
                    last_msg = conv.messages[-1] if conv.messages else {}
                    content = last_msg.get("content", "")[:40]
                    conv_lines.append(f"- 会话 {conv.session_id}: {content}...")
            parts.append("【近期会话摘要】\n" + "\n".join(conv_lines))

        # 3. 近期作品
        if include_recent_scripts and ctx.recent_scripts:
            script_lines = []
            for sc in ctx.recent_scripts[:max_scripts]:
                info = sc.title or sc.script_id
                if sc.script_type:
                    info += f" ({sc.script_type})"
                if sc.rating is not None:
                    info += f" [评分: {sc.rating}]"
                script_lines.append(f"- {info}")
            parts.append("【近期作品】\n" + "\n".join(script_lines))

        # Token 预算控制：从低优先级开始截断
        full_text = "\n\n".join(parts)
        if _estimate_tokens(full_text) <= max_tokens:
            return full_text

        # 逐段截断
        truncated: list[str] = []
        current_tokens = 0
        for part in parts:
            part_tokens = _estimate_tokens(part)
            if current_tokens + part_tokens > max_tokens:
                if not truncated:
                    # 第一段就超预算：强行截断
                    part = _truncate_text(part, max_tokens)
                else:
                    break
            truncated.append(part)
            current_tokens += _estimate_tokens(part)
            if current_tokens >= max_tokens:
                break

        result = "\n\n".join(truncated)
        if len(truncated) < len(parts):
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
