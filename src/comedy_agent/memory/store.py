"""记忆存储 —— 抽象基类接口定义。

定义短期记忆（会话级）与中期记忆（用户级）的统一读写接口。
具体实现由子类提供（如 SQLMemoryStore、RedisShortTermMemory 等）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from comedy_agent.memory.models import (
    BannedWordData,
    ConversationData,
    DocumentData,
    EarningRecordData,
    IPStyleData,
    KnowledgeCardData,
    PersonaData,
    PreferenceItem,
    ProjectData,
    SaltHistoryData,
    ScriptData,
    SubmissionData,
    TokenAccountData,
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
        source: str = "chat",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """保存会话记录。

        Args:
            user_id: 用户唯一标识。
            session_id: 会话唯一标识。
            messages: 消息列表，格式为 ``[{"role": "human", "content": "..."}, ...]``。
            summary: 可选的对话摘要。
            source: 来源标识，如 chat / salt / actor。
            metadata: 额外元数据。
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

    # ------------------------------------------------------------------ #
    # 知识卡片（技巧库）
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_knowledge_card(self, card: KnowledgeCardData) -> KnowledgeCardData:
        """保存或更新知识卡片。

        Args:
            card: 知识卡片数据。

        Returns:
            KnowledgeCardData: 保存后的卡片数据。
        """
        ...

    @abstractmethod
    def list_knowledge_cards(
        self, user_id: str, card_type: str | None = None, tag: str | None = None
    ) -> list[KnowledgeCardData]:
        """列出用户的知识卡片。

        Args:
            user_id: 用户唯一标识。
            card_type: 可选的卡片类型过滤。
            tag: 可选的标签过滤。

        Returns:
            list[KnowledgeCardData]: 卡片列表。
        """
        ...

    @abstractmethod
    def get_knowledge_card(self, user_id: str, card_id: str) -> KnowledgeCardData | None:
        """获取单个知识卡片。

        Args:
            user_id: 用户唯一标识。
            card_id: 卡片唯一标识。

        Returns:
            KnowledgeCardData: 卡片数据，不存在则返回 None。
        """
        ...

    @abstractmethod
    def delete_knowledge_card(self, user_id: str, card_id: str) -> bool:
        """删除知识卡片。

        Args:
            user_id: 用户唯一标识。
            card_id: 卡片唯一标识。

        Returns:
            bool: 是否成功删除。
        """
        ...

    # ------------------------------------------------------------------ #
    # Token 账户
    # ------------------------------------------------------------------ #
    @abstractmethod
    def get_token_account(self, user_id: str) -> TokenAccountData | None:
        """获取用户 Token 账户。"""
        ...

    @abstractmethod
    def deduct_tokens(self, user_id: str, amount: int) -> bool:
        """扣减用户 Token 余额。

        Returns:
            bool: 是否扣减成功（余额不足时返回 False）。
        """
        ...

    @abstractmethod
    def recharge_tokens(self, user_id: str, amount: int) -> TokenAccountData:
        """充值用户 Token 余额。"""
        ...

    # ------------------------------------------------------------------ #
    # 项目
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_project(self, user_id: str, project: ProjectData) -> ProjectData:
        """保存或更新项目。"""
        ...

    @abstractmethod
    def load_project(self, user_id: str, project_id: str) -> ProjectData | None:
        """读取指定项目。"""
        ...

    @abstractmethod
    def list_projects(self, user_id: str) -> list[ProjectData]:
        """列出用户所有项目，按更新时间倒序。"""
        ...

    @abstractmethod
    def delete_project(self, user_id: str, project_id: str) -> bool:
        """删除项目。"""
        ...

    # ------------------------------------------------------------------ #
    # 加点盐历史
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_salt_history(self, history: SaltHistoryData) -> SaltHistoryData:
        """保存加点盐历史记录。"""
        ...

    @abstractmethod
    def list_salt_history(self, user_id: str, project_id: str | None = None) -> list[SaltHistoryData]:
        """列出用户的加点盐历史。"""
        ...

    # ------------------------------------------------------------------ #
    # IP 风格模型
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_ip_style(self, style: IPStyleData) -> IPStyleData:
        """保存或更新 IP 风格模型。"""
        ...

    @abstractmethod
    def load_ip_style(self, style_id: str) -> IPStyleData | None:
        """读取指定 IP 风格模型。"""
        ...

    @abstractmethod
    def list_ip_styles(self, status: str | None = None) -> list[IPStyleData]:
        """列出 IP 风格模型，支持按状态过滤。"""
        ...

    @abstractmethod
    def delete_ip_style(self, style_id: str) -> bool:
        """删除 IP 风格模型。"""
        ...

    # ------------------------------------------------------------------ #
    # 人物画像 (Persona)
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_persona(self, persona: PersonaData) -> PersonaData:
        """保存或更新人物画像。"""
        ...

    @abstractmethod
    def load_persona(self, persona_id: str) -> PersonaData | None:
        """读取指定人物画像。"""
        ...

    @abstractmethod
    def list_personas(
        self, creator_id: str | None = None, org_id: str | None = None, is_active: bool | None = None
    ) -> list[PersonaData]:
        """列出人物画像，支持按创建者、组织、状态过滤。"""
        ...

    @abstractmethod
    def delete_persona(self, persona_id: str) -> bool:
        """删除人物画像。"""
        ...

    # ------------------------------------------------------------------ #
    # 投稿
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_submission(self, submission: SubmissionData) -> SubmissionData:
        """保存投稿。"""
        ...

    @abstractmethod
    def load_submission(self, submission_id: str) -> SubmissionData | None:
        """读取指定投稿。"""
        ...

    @abstractmethod
    def list_submissions(
        self, user_id: str | None = None, target_actor: str | None = None, status: str | None = None
    ) -> list[SubmissionData]:
        """列出投稿，支持按用户、目标演员、状态过滤。"""
        ...

    @abstractmethod
    def review_submission(self, submission_id: str, status: str, comment: str | None = None) -> bool:
        """审核投稿。"""
        ...

    # ------------------------------------------------------------------ #
    # 收益记录
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_earning(self, record: EarningRecordData) -> EarningRecordData:
        """保存收益记录。"""
        ...

    @abstractmethod
    def list_earnings(self, user_id: str | None = None, actor_name: str | None = None) -> list[EarningRecordData]:
        """列出收益记录。"""
        ...

    # ------------------------------------------------------------------ #
    # 敏感词
    # ------------------------------------------------------------------ #
    @abstractmethod
    def save_banned_word(self, word: BannedWordData) -> BannedWordData:
        """保存敏感词。"""
        ...

    @abstractmethod
    def list_banned_words(self, category: str | None = None) -> list[BannedWordData]:
        """列出敏感词，支持按分类过滤。"""
        ...

    @abstractmethod
    def delete_banned_word(self, word_id: int) -> bool:
        """删除敏感词。"""
        ...

    # ------------------------------------------------------------------ #
    # 统计
    # ------------------------------------------------------------------ #
    @abstractmethod
    def get_user_stats(self, user_id: str) -> dict[str, Any]:
        """获取用户使用统计。

        Args:
            user_id: 用户唯一标识。

        Returns:
            dict: 包含 generations, actor_usage, salt_usage, earnings 的统计字典。
        """
        ...
