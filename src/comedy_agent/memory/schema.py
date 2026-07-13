"""记忆库 SQLAlchemy ORM Schema。

定义用户画像、偏好、会话、作品四张核心表。
所有数据存储于 SQLite（开发阶段），未来可无缝迁移到 PostgreSQL。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
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
    bio: Mapped[str | None] = mapped_column(Text, nullable=True, comment="个人简介")
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, comment="兴趣标签")
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="头像 URL")
    is_verified: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="是否认证大V"
    )
    knowledge_shared: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="知识库是否共享给其他用户"
    )
    follower_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="粉丝数"
    )
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
    token_account: Mapped["UserTokenAccount"] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    projects: Mapped[list["UserProject"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    salt_history: Mapped[list["SaltHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    submissions: Mapped[list["ScriptSubmission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    earnings: Mapped[list["EarningRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    consumption_records: Mapped[list["TokenConsumptionRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    personas: Mapped[list["Persona"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    followers: Mapped[list["Follow"]] = relationship(
        foreign_keys="Follow.following_id",
        back_populates="following_user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    following: Mapped[list["Follow"]] = relationship(
        foreign_keys="Follow.follower_id",
        back_populates="follower_user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


# ------------------------------------------------------------------ #
# Follow —— 关注关系
# ------------------------------------------------------------------ #
class Follow(Base):
    """关注关系表。"""

    __tablename__ = "follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="uq_follow"),
    )

    follow_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    follower_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    following_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    follower_user: Mapped["UserProfile"] = relationship(
        foreign_keys=[follower_id], back_populates="following"
    )
    following_user: Mapped["UserProfile"] = relationship(
        foreign_keys=[following_id], back_populates="followers"
    )


# ------------------------------------------------------------------ #
# VerificationApplication —— 认证申请
# ------------------------------------------------------------------ #
class VerificationApplication(Base):
    """用户认证（大V）申请表。"""

    __tablename__ = "verification_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, comment="pending / approved / rejected"
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="申请理由")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="审核备注")
    applied_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


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
    source: Mapped[str] = mapped_column(String(16), default="chat", nullable=False)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
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
        String(32), nullable=True, comment="standup"
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
        String(32), nullable=True, comment="喜剧种类：standup / general"
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


# ------------------------------------------------------------------ #
# UserTokenAccount —— 用户 Token 账户
# ------------------------------------------------------------------ #
class UserTokenAccount(Base):
    """用户 Token 账户表。"""

    __tablename__ = "user_token_accounts"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance: Mapped[int] = mapped_column(Integer, default=5000, nullable=False)
    total_consumed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_recharged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="token_account")


# ------------------------------------------------------------------ #
# UserProject —— 用户项目
# ------------------------------------------------------------------ #
class UserProject(Base):
    """用户项目表。"""

    __tablename__ = "user_projects"

    project_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    project_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="standup / salt / mixed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="projects")


# ------------------------------------------------------------------ #
# SaltHistory —— 加点盐历史
# ------------------------------------------------------------------ #
class SaltHistory(Base):
    """加点盐历史表。"""

    __tablename__ = "salt_history"

    salt_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_projects.project_id"), nullable=True
    )
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    polished_text: Mapped[str] = mapped_column(Text, nullable=False)
    salt_level: Mapped[str] = mapped_column(String(16), nullable=False)
    token_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="salt_history")


# ------------------------------------------------------------------ #
# IPStyle —— IP 风格模型
# ------------------------------------------------------------------ #
class IPStyle(Base):
    """IP 风格模型表（扩展为 IP 角色）。"""

    __tablename__ = "ip_styles"

    style_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    actor_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="active", nullable=False, comment="active / testing / offline"
    )
    split_ratio: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # --- PRD v2 扩展字段 ---
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="角色头像 URL")
    homepage_background: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="主页背景图 URL"
    )
    profile_url: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="个人主页路径，如 /ip/lidan"
    )
    follower_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="粉丝数")
    is_official: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="是否官方认证角色"
    )
    skill_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="关联的风格 Skill ID"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


# ------------------------------------------------------------------ #
# Persona —— 人物画像（写作 Rules）
# ------------------------------------------------------------------ #
class Persona(Base):
    """人物画像表。存储用户预设的写作规则约束。"""

    __tablename__ = "personas"

    persona_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    org_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="组织 ID"
    )
    creator_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="画像名称")
    description: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="画像描述"
    )
    rule_content: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False, comment="结构化写作约束 JSON"
    )
    skill_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="关联的 rule 类型 Skill ID"
    )
    reference_files: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, comment="参考文件列表"
    )
    is_active: Mapped[bool] = mapped_column(
        default=True, nullable=False, comment="是否启用"
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="personas")


# ------------------------------------------------------------------ #
# ScriptSubmission —— 用户投稿
# ------------------------------------------------------------------ #
class ScriptSubmission(Base):
    """用户投稿表。"""

    __tablename__ = "script_submissions"

    submission_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    script_id: Mapped[str] = mapped_column(
        ForeignKey("user_scripts.script_id"), nullable=False
    )
    target_actor: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, comment="pending / adopted / rejected"
    )
    actor_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="submissions")


# ------------------------------------------------------------------ #
# EarningRecord —— 收益记录
# ------------------------------------------------------------------ #
class EarningRecord(Base):
    """收益记录表。"""

    __tablename__ = "earning_records"

    record_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    actor_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    record_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="earnings")


# ------------------------------------------------------------------ #
# TokenConsumptionRecord —— Token 消费记录
# ------------------------------------------------------------------ #
class TokenConsumptionRecord(Base):
    """模型调用 Token 消费记录表。"""

    __tablename__ = "token_consumption_records"

    consumption_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="用户 ID",
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="关联会话 ID"
    )
    endpoint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="调用入口，如 /chat /salt /pro/generate"
    )
    model: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="实际使用的模型名"
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="输入 Token 数"
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="输出 Token 数"
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="总 Token 数"
    )
    cost: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="扣除的 Token 数"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="描述，如极速版润色"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationship
    user: Mapped["UserProfile"] = relationship(back_populates="consumption_records")


# ------------------------------------------------------------------ #
# BannedWord —— 敏感词
# ------------------------------------------------------------------ #
class FeedbackEvent(Base):
    """用户反馈事件表。

    记录消息/Artifact 级的 👍/👎 反馈，用于后续数据回流和模型改进。
    """

    __tablename__ = "feedback_events"

    event_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="用户 ID"
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True, comment="会话 ID"
    )
    target_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="message / artifact"
    )
    target_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="消息索引或 artifact id"
    )
    rating: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="1 赞 / -1 踩 / 0 撤销"
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="文字反馈")
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="原始内容、artifact 类型等 JSON"
    )
    ingested: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="是否已回流到向量库"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class BannedWord(Base):
    """敏感词配置表。"""

    __tablename__ = "banned_words"

    word_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="political / competitor / vulgar"
    )
    added_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


# ------------------------------------------------------------------ #
# EvalSession —— 笑果评测会话
# ------------------------------------------------------------------ #
class EvalSession(Base):
    """笑果评测会话表。"""

    __tablename__ = "eval_sessions"

    session_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    skill_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    topic: Mapped[str] = mapped_column(String(256), nullable=False)
    attitude: Mapped[str] = mapped_column(String(128), nullable=False)
    bias: Mapped[str] = mapped_column(String(512), nullable=False)
    emotion: Mapped[str] = mapped_column(String(128), nullable=False)
    duration: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="running", nullable=False, comment="running / done / failed"
    )
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationship
    results: Mapped[list["EvalResult"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )


class EvalResult(Base):
    """笑果评测结果表。"""

    __tablename__ = "eval_results"

    result_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("eval_sessions.session_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    section_title: Mapped[str] = mapped_column(String(256), nullable=False)
    section_body: Mapped[str] = mapped_column(Text, nullable=False)
    combo_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="章节组合 ID"
    )
    combo_sections: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, comment="组合包含的章节列表"
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, comment="pending / running / done / failed"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="bad / ok / top"
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationship
    session: Mapped["EvalSession"] = relationship(back_populates="results")
