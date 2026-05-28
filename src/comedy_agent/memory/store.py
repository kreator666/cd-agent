"""记忆存储 —— 抽象基类接口定义。

定义短期记忆（会话级）与中期记忆（用户级）的统一读写接口。
具体实现由子类提供（如 SQLMemoryStore、RedisShortTermMemory 等）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from comedy_agent.memory.models import (
    ConversationData,
    DocumentData,
    PreferenceItem,
    ScriptData,
    UserContext,
    UserProfileData,
)


class MemoryStore(ABC):
    """记忆存储抽象基类。"""

    # ------------------------------------------------------------------ #
    # 用户画像
    # ------------------------------------------------------------------ #
    @abstractmethod
    def get_or_create_user(
        self, user_id: str, nickname: str | None = None
    ) -> UserProfileData:
        """获取或创建用户画像。

        Args:
            user_id: 用户唯一标识。
            nickname: 用户昵称（首次创建时有效）。

        Returns:
            UserProfileData: 用户画像数据。
        """
        ...

    # ------------------------------------------------------------------ #
    # 短期记忆 —— 会话记录
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_conversation(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        summary: str | None = None,
    ) -> None:
        """保存会话记录。

        Args:
            user_id: 用户唯一标识。
            session_id: 会话唯一标识。
            messages: 消息列表，格式为 ``[{"role": "human", "content": "..."}, ...]``。
            summary: 可选的对话摘要。
        """
        ...

    @abstractmethod
    def load_conversation(
        self, user_id: str, session_id: str
    ) -> ConversationData | None:
        """读取指定会话记录。

        Args:
            user_id: 用户唯一标识。
            session_id: 会话唯一标识。

        Returns:
            ConversationData: 会话数据，若不存在或已过期则返回 ``None``。
        """
        ...

    @abstractmethod
    def list_conversations(
        self, user_id: str, limit: int = 10
    ) -> list[ConversationData]:
        """列出用户最近的会话记录（自动过滤已过期）。

        Args:
            user_id: 用户唯一标识。
            limit: 最大返回数量。

        Returns:
            list[ConversationData]: 会话数据列表，按更新时间倒序。
        """
        ...

    @abstractmethod
    def delete_conversation(self, user_id: str, session_id: str) -> bool:
        """删除指定会话记录。

        Args:
            user_id: 用户唯一标识。
            session_id: 会话唯一标识。

        Returns:
            bool: 是否成功删除。
        """
        ...

    # ------------------------------------------------------------------ #
    # 中期记忆 —— 用户偏好
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_preference(self, user_id: str, key: str, value: Any) -> None:
        """保存用户偏好。

        Args:
            user_id: 用户唯一标识。
            key: 偏好键，如 ``preferred_style``、``disliked_tropes``。
            value: 偏好值，任意 JSON 可序列化结构。
        """
        ...

    @abstractmethod
    def load_preference(self, user_id: str, key: str) -> Any | None:
        """读取指定用户偏好。

        Args:
            user_id: 用户唯一标识。
            key: 偏好键。

        Returns:
            Any: 偏好值，若不存在则返回 ``None``。
        """
        ...

    @abstractmethod
    def list_preferences(self, user_id: str) -> list[PreferenceItem]:
        """列出用户所有偏好。

        Args:
            user_id: 用户唯一标识。

        Returns:
            list[PreferenceItem]: 偏好列表。
        """
        ...

    # ------------------------------------------------------------------ #
    # 中期记忆 —— 用户创作作品
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_script(self, user_id: str, script: ScriptData) -> ScriptData:
        """保存用户创作作品。

        Args:
            user_id: 用户唯一标识。
            script: 作品数据。

        Returns:
            ScriptData: 保存后的作品数据（包含自动生成的 script_id）。
        """
        ...

    @abstractmethod
    def load_script(self, script_id: str) -> ScriptData | None:
        """读取指定作品。

        Args:
            script_id: 作品唯一标识。

        Returns:
            ScriptData: 作品数据，若不存在则返回 ``None``。
        """
        ...

    @abstractmethod
    def list_scripts(
        self, user_id: str, script_type: str | None = None, min_rating: float | None = None
    ) -> list[ScriptData]:
        """列出用户作品。

        Args:
            user_id: 用户唯一标识。
            script_type: 可选的作品类型过滤。
            min_rating: 可选的最低评分过滤。

        Returns:
            list[ScriptData]: 作品列表，按创建时间倒序。
        """
        ...

    @abstractmethod
    def list_all_scripts(
        self, min_rating: float | None = None
    ) -> list[ScriptData]:
        """列出所有用户作品（跨用户）。

        Args:
            min_rating: 可选的最低评分过滤。

        Returns:
            list[ScriptData]: 作品列表，按评分降序。
        """
        ...

    @abstractmethod
    def delete_script(self, script_id: str) -> bool:
        """删除指定作品。

        Args:
            script_id: 作品唯一标识。

        Returns:
            bool: 是否成功删除。
        """
        ...

    @abstractmethod
    def rate_script(self, script_id: str, rating: float) -> bool:
        """为作品评分。

        Args:
            script_id: 作品唯一标识。
            rating: 评分 0.0–5.0。

        Returns:
            bool: 是否成功更新评分。
        """
        ...

    # ------------------------------------------------------------------ #
    # 上下文构建（供 Agent 使用）
    # ------------------------------------------------------------------ #
    @abstractmethod
    def build_user_context(
        self, user_id: str, max_conversations: int = 3
    ) -> UserContext:
        """构建用户完整上下文，供注入 Agent Prompt 使用。

        Args:
            user_id: 用户唯一标识。
            max_conversations: 最大历史会话数。

        Returns:
            UserContext: 包含画像、偏好、近期会话、近期作品的完整上下文。
        """
        ...

    # ------------------------------------------------------------------ #
    # 用户文档（知识库上传）
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_document(self, document: DocumentData) -> DocumentData:
        """保存或更新用户上传文档记录。

        Args:
            document: 文档数据。

        Returns:
            DocumentData: 保存后的文档数据（包含自动生成的 doc_id）。
        """
        ...

    @abstractmethod
    def list_documents(self, user_id: str) -> list[DocumentData]:
        """列出用户上传的所有文档。

        Args:
            user_id: 用户唯一标识。

        Returns:
            list[DocumentData]: 文档列表，按创建时间倒序。
        """
        ...

    @abstractmethod
    def get_document(self, user_id: str, doc_id: str) -> DocumentData | None:
        """获取单个文档记录。

        Args:
            user_id: 用户唯一标识。
            doc_id: 文档唯一标识。

        Returns:
            DocumentData: 文档数据，不存在则返回 None。
        """
        ...

    @abstractmethod
    def delete_document(self, user_id: str, doc_id: str) -> bool:
        """删除用户文档记录。

        Args:
            user_id: 用户唯一标识。
            doc_id: 文档唯一标识。

        Returns:
            bool: 是否成功删除。
        """
        ...
