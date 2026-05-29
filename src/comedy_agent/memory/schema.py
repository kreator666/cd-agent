"""记忆库 SQLAlchemy ORM Schema。

定义用户画像、偏好、会话、作品四张核心表。
所有数据存储于 SQLite（开发阶段），未来可无缝迁移到 PostgreSQL。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""

    pass


# ------------------------------------------------------------------ #
# UserProfile —— 用户画像
# ------------------------------------------------------------------ #
class UserProfile(Base):
    """用户画像表。"""

    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nickname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    preferences: Mapped[list["UserPreference"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    conversations: Mapped[list["UserConversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    scripts: Mapped[list["UserScript"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    documents: Mapped[list["UserDocument"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    knowledge_cards: Mapped[list["KnowledgeCard"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


# ------------------------------------------------------------------ #
# UserPreference —— 用户偏好（KV 结构，JSON value）
# ------------------------------------------------------------------ #
class UserPreference(Base):
    """用户偏好表。支持任意结构化 JSON value。"""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="preferences")


# ------------------------------------------------------------------ #
# UserConversation —— 会话记录（短期记忆）
# ------------------------------------------------------------------ #
class UserConversation(Base):
    """会话记录表。存储最近 N 轮对话，支持 expires_at 惰性过期。"""

    __tablename__ = "user_conversations"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="conversations")


# ------------------------------------------------------------------ #
# UserScript —— 用户创作作品库
# ------------------------------------------------------------------ #
class UserScript(Base):
    """用户创作作品表。支持评分、标签、类型。"""

    __tablename__ = "user_scripts"

    script_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    script_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="standup/sketch/crosstalk/sitcom"
    )
    rating: Mapped[float | None] = mapped_column(nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="scripts")


# ------------------------------------------------------------------ #
# UserDocument —— 用户上传的知识库文档
# ------------------------------------------------------------------ #
class UserDocument(Base):
    """用户上传文档表。记录文档元数据及解析入库状态。"""

    __tablename__ = "user_documents"

    doc_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    doc_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="theory / case / mixed"
    )
    kind: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="喜剧种类：standup / sketch / manzai / japanese_sketch / crosstalk / sitcom / general"
    )
    style: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="风格标识：traditional / modern / 自嘲 / 讽刺 / 愤怒式 / 荒诞式 / 日常观察"
    )
    chunk_strategy: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="分块策略：fixed / paragraph / scene / dialogue / subtitle"
    )
    topic: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="文档主题/话题，如：职场加班、相亲经历"
    )
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, comment="pending / ingested / failed"
    )
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="documents")


# ------------------------------------------------------------------ #
# KnowledgeCard —— 知识卡片（技巧/概念/公式/模式）
# ------------------------------------------------------------------ #
class KnowledgeCard(Base):
    """知识卡片表。存储从文档中提取或手动创建的结构化技巧。"""

    __tablename__ = "knowledge_cards"

    card_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    card_type: Mapped[str] = mapped_column(
        String(32), default="technique", nullable=False, comment="technique / concept / formula / pattern"
    )
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    source_doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="knowledge_cards")
