"""中期记忆 SQL 实现 —— SQLMemoryStore。

基于 SQLAlchemy + SQLite，实现 MemoryStore 抽象基类的全部接口。
支持用户画像、会话、作品的完整 CRUD。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from comedy_agent.core.config import settings
from comedy_agent.memory.models import (
    BannedWordData,
    ConversationData,
    DocumentData,
    EarningRecordData,
    IPStyleData,
    KnowledgeCardData,
    ProjectData,
    SaltHistoryData,
    ScriptData,
    SubmissionData,
    TokenAccountData,
    UserContext,
    UserProfileData,
)
from comedy_agent.memory.schema import (
    Base,
    BannedWord,
    EarningRecord,
    IPStyle,
    KnowledgeCard,
    SaltHistory,
    ScriptSubmission,
    UserConversation,
    UserDocument,
    UserPreference,
    UserProfile,
    UserProject,
    UserScript,
    UserTokenAccount,
)
from comedy_agent.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class SQLMemoryStore(MemoryStore):
    """基于 SQLite 的记忆存储实现。

    覆盖短期记忆（会话）与中期记忆（作品）的全部操作。
    """

    def __init__(self, db_url: str | None = None) -> None:
        """初始化 SQLMemoryStore。

        Args:
            db_url: 数据库连接 URL，默认使用 ``settings.memory_db_path``。
                支持内存数据库 ``sqlite:///:memory:``（主要用于测试）。
        """
        if db_url is None:
            db_path = settings.memory_db_path
            db_url = f"sqlite:///{db_path}"
        self.engine = create_engine(db_url, echo=False)
        # 对文件数据库启用 WAL 模式，提升并发读取性能
        if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:///:memory:"):
            with self.engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL")
                conn.commit()
        Base.metadata.create_all(self.engine)
        # 简单迁移：为旧表添加缺失列（开发阶段兼容）
        with self.engine.connect() as conn:
            # user_profiles.password_hash
            columns = [
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(user_profiles)")
            ]
            if "password_hash" not in columns:
                conn.exec_driver_sql(
                    "ALTER TABLE user_profiles ADD COLUMN password_hash VARCHAR(256)"
                )
                conn.commit()
                logger.info("Migrated user_profiles: added password_hash column")
            # user_conversations.source / metadata
            conv_columns = [
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(user_conversations)")
            ]
            if "source" not in conv_columns:
                conn.exec_driver_sql(
                    "ALTER TABLE user_conversations ADD COLUMN source VARCHAR(16) DEFAULT 'chat'"
                )
                conn.commit()
                logger.info("Migrated user_conversations: added source column")
            if "extra_metadata" not in conv_columns:
                conn.exec_driver_sql(
                    "ALTER TABLE user_conversations ADD COLUMN extra_metadata JSON"
                )
                conn.commit()
                logger.info("Migrated user_conversations: added extra_metadata column")
        self.Session = sessionmaker(bind=self.engine)
        logger.info("SQLMemoryStore initialized: %s", db_url)

    # ------------------------------------------------------------------ #
    # 辅助方法
    # ------------------------------------------------------------------ #
    def _new_session(self):
        """创建新 Session（支持上下文管理）。"""
        return self.Session()

    @staticmethod
    def _now() -> datetime:
        """返回当前 UTC 时间。"""
        return datetime.utcnow()

    @staticmethod
    def _is_expired(row: UserConversation) -> bool:
        """判断会话记录是否已过期。"""
        if row.expires_at is None:
            return False
        return datetime.utcnow() > row.expires_at

    # ------------------------------------------------------------------ #
    # 用户画像
    # ------------------------------------------------------------------ #
    def get_or_create_user(
        self, user_id: str, nickname: str | None = None
    ) -> UserProfileData:
        with self._new_session() as session:
            user = session.query(UserProfile).filter_by(user_id=user_id).first()
            if user is None:
                user = UserProfile(user_id=user_id, nickname=nickname)
                session.add(user)
                session.commit()
                logger.debug("Created user profile: %s", user_id)
            return UserProfileData(
                user_id=user.user_id,
                nickname=user.nickname,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )

    def create_user(
        self, user_id: str, password_hash: str, nickname: str | None = None
    ) -> UserProfileData:
        """创建带密码的用户画像。"""
        with self._new_session() as session:
            existing = session.query(UserProfile).filter_by(user_id=user_id).first()
            if existing is not None:
                raise ValueError(f"用户 '{user_id}' 已存在")
            user = UserProfile(user_id=user_id, nickname=nickname, password_hash=password_hash)
            session.add(user)
            session.commit()
            logger.info("Created user with password: %s", user_id)
            return UserProfileData(
                user_id=user.user_id,
                nickname=user.nickname,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )

    def get_user_password_hash(self, user_id: str) -> str | None:
        """获取用户的密码哈希。"""
        with self._new_session() as session:
            user = session.query(UserProfile).filter_by(user_id=user_id).first()
            return user.password_hash if user else None

    def get_user(self, user_id: str) -> UserProfileData | None:
        """根据 user_id 获取用户画像。"""
        with self._new_session() as session:
            user = session.query(UserProfile).filter_by(user_id=user_id).first()
            if user is None:
                return None
            return UserProfileData(
                user_id=user.user_id,
                nickname=user.nickname,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )

    # ------------------------------------------------------------------ #
    # 短期记忆 —— 会话
    # ------------------------------------------------------------------ #
    def save_conversation(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        summary: str | None = None,
        source: str = "chat",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._new_session() as session:
            conv = (
                session.query(UserConversation)
                .filter_by(session_id=session_id)
                .first()
            )
            if conv is None:
                conv = UserConversation(
                    session_id=session_id,
                    user_id=user_id,
                    messages=messages,
                    summary=summary,
                    source=source,
                    extra_metadata=metadata,
                    expires_at=self._now() + timedelta(hours=24),
                )
                session.add(conv)
            else:
                conv.messages = messages
                conv.summary = summary
                conv.source = source
                if metadata is not None:
                    conv.extra_metadata = metadata
                conv.updated_at = self._now()
            session.commit()
            logger.debug("Saved conversation: %s (%s)", session_id, source)

    def load_conversation(
        self, user_id: str, session_id: str
    ) -> ConversationData | None:
        with self._new_session() as session:
            conv = (
                session.query(UserConversation)
                .filter_by(session_id=session_id, user_id=user_id)
                .first()
            )
            if conv is None or self._is_expired(conv):
                return None
            return ConversationData(
                session_id=conv.session_id,
                messages=conv.messages,
                summary=conv.summary,
                source=conv.source,
                metadata=conv.extra_metadata,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                expires_at=conv.expires_at,
            )

    def list_conversations(
        self, user_id: str, limit: int = 10
    ) -> list[ConversationData]:
        with self._new_session() as session:
            rows = (
                session.query(UserConversation)
                .filter_by(user_id=user_id)
                .order_by(
                    UserConversation.updated_at.desc(),
                    UserConversation.session_id.desc(),
                )
                .limit(limit)
                .all()
            )
            results: list[ConversationData] = []
            for row in rows:
                if self._is_expired(row):
                    continue
                results.append(
                    ConversationData(
                        session_id=row.session_id,
                        messages=row.messages,
                        summary=row.summary,
                        source=row.source,
                        metadata=row.extra_metadata,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        expires_at=row.expires_at,
                    )
                )
            return results

    def delete_conversation(self, user_id: str, session_id: str) -> bool:
        """删除指定会话记录。"""
        with self._new_session() as session:
            row = (
                session.query(UserConversation)
                .filter_by(session_id=session_id, user_id=user_id)
                .first()
            )
            if row is None:
                return False
            session.delete(row)
            session.commit()
            logger.debug("Deleted conversation: %s", session_id)
            return True

    # ------------------------------------------------------------------ #
    # 中期记忆 —— 偏好（已弃用，保留空实现以兼容抽象基类）
    # ------------------------------------------------------------------ #
    def save_preference(self, user_id: str, key: str, value: Any) -> None:
        pass

    def load_preference(self, user_id: str, key: str) -> Any | None:
        return None

    def list_preferences(self, user_id: str) -> list[Any]:
        return []

    # ------------------------------------------------------------------ #
    # 中期记忆 —— 作品
    # ------------------------------------------------------------------ #
    def save_script(self, user_id: str, script: ScriptData) -> ScriptData:
        script_id = script.script_id or uuid.uuid4().hex[:16]
        with self._new_session() as session:
            row = (
                session.query(UserScript)
                .filter_by(script_id=script_id)
                .first()
            )
            if row is None:
                row = UserScript(
                    script_id=script_id,
                    user_id=user_id,
                    title=script.title,
                    content=script.content,
                    script_type=script.script_type,
                    rating=script.rating,
                    tags=script.tags,
                )
                session.add(row)
            else:
                row.title = script.title
                row.content = script.content
                row.script_type = script.script_type
                row.rating = script.rating
                row.tags = script.tags
                row.updated_at = self._now()
            session.commit()
            logger.debug("Saved script: %s", script_id)
            return ScriptData(
                script_id=row.script_id,
                title=row.title,
                content=row.content,
                script_type=row.script_type,
                rating=row.rating,
                tags=row.tags,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def load_script(self, script_id: str) -> ScriptData | None:
        with self._new_session() as session:
            row = (
                session.query(UserScript).filter_by(script_id=script_id).first()
            )
            if row is None:
                return None
            return ScriptData(
                script_id=row.script_id,
                title=row.title,
                content=row.content,
                script_type=row.script_type,
                rating=row.rating,
                tags=row.tags,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def list_scripts(
        self, user_id: str, script_type: str | None = None, min_rating: float | None = None
    ) -> list[ScriptData]:
        with self._new_session() as session:
            query = session.query(UserScript).filter_by(user_id=user_id)
            if script_type:
                query = query.filter_by(script_type=script_type)
            if min_rating is not None:
                query = query.filter(UserScript.rating >= min_rating)
            rows = query.order_by(UserScript.created_at.desc()).all()
            return [
                ScriptData(
                    script_id=r.script_id,
                    title=r.title,
                    content=r.content,
                    script_type=r.script_type,
                    rating=r.rating,
                    tags=r.tags,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]

    def list_all_scripts(
        self, min_rating: float | None = None
    ) -> list[ScriptData]:
        with self._new_session() as session:
            query = session.query(UserScript)
            if min_rating is not None:
                query = query.filter(UserScript.rating >= min_rating)
            rows = query.order_by(UserScript.rating.desc()).all()
            return [
                ScriptData(
                    script_id=r.script_id,
                    title=r.title,
                    content=r.content,
                    script_type=r.script_type,
                    rating=r.rating,
                    tags=r.tags,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]

    def delete_script(self, script_id: str) -> bool:
        with self._new_session() as session:
            row = (
                session.query(UserScript).filter_by(script_id=script_id).first()
            )
            if row is None:
                return False
            session.delete(row)
            session.commit()
            logger.debug("Deleted script: %s", script_id)
            return True

    def rate_script(self, script_id: str, rating: float) -> bool:
        with self._new_session() as session:
            row = (
                session.query(UserScript).filter_by(script_id=script_id).first()
            )
            if row is None:
                return False
            row.rating = rating
            row.updated_at = self._now()
            session.commit()
            logger.debug("Rated script: %s -> %.1f", script_id, rating)
            return True

    # ------------------------------------------------------------------ #
    # 用户文档（知识库上传）
    # ------------------------------------------------------------------ #
    def save_document(self, document: DocumentData) -> DocumentData:
        """保存或更新用户上传文档记录。"""
        with self._new_session() as session:
            existing = (
                session.query(UserDocument)
                .filter_by(doc_id=document.doc_id, user_id=document.user_id)
                .first()
            )
            if existing is None:
                row = UserDocument(
                    doc_id=document.doc_id or uuid.uuid4().hex[:16],
                    user_id=document.user_id,
                    filename=document.filename,
                    doc_type=document.doc_type,
                    kind=document.kind,
                    style=document.style,
                    chunk_strategy=document.chunk_strategy,
                    topic=document.topic,
                    status=document.status,
                    chunk_count=document.chunk_count,
                    error_msg=document.error_msg,
                )
                session.add(row)
            else:
                existing.filename = document.filename
                existing.doc_type = document.doc_type
                existing.kind = document.kind
                existing.style = document.style
                existing.chunk_strategy = document.chunk_strategy
                existing.topic = document.topic
                existing.status = document.status
                existing.chunk_count = document.chunk_count
                existing.error_msg = document.error_msg
            session.commit()
            row = (
                session.query(UserDocument)
                .filter_by(doc_id=(row.doc_id if existing is None else existing.doc_id))
                .first()
            )
            return DocumentData(
                doc_id=row.doc_id,
                user_id=row.user_id,
                filename=row.filename,
                doc_type=row.doc_type,
                kind=row.kind,
                style=row.style,
                chunk_strategy=row.chunk_strategy,
                topic=row.topic,
                status=row.status,
                chunk_count=row.chunk_count,
                error_msg=row.error_msg,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def list_documents(self, user_id: str) -> list[DocumentData]:
        """列出用户上传的所有文档，按创建时间倒序。"""
        with self._new_session() as session:
            rows = (
                session.query(UserDocument)
                .filter_by(user_id=user_id)
                .order_by(UserDocument.created_at.desc())
                .all()
            )
            return [
                DocumentData(
                    doc_id=r.doc_id,
                    user_id=r.user_id,
                    filename=r.filename,
                    doc_type=r.doc_type,
                    kind=r.kind,
                    style=r.style,
                    chunk_strategy=r.chunk_strategy,
                    status=r.status,
                    chunk_count=r.chunk_count,
                    error_msg=r.error_msg,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]

    def get_document(self, user_id: str, doc_id: str) -> DocumentData | None:
        """获取单个文档记录。"""
        with self._new_session() as session:
            row = (
                session.query(UserDocument)
                .filter_by(doc_id=doc_id, user_id=user_id)
                .first()
            )
            if row is None:
                return None
            return DocumentData(
                doc_id=row.doc_id,
                user_id=row.user_id,
                filename=row.filename,
                doc_type=row.doc_type,
                kind=row.kind,
                style=row.style,
                chunk_strategy=row.chunk_strategy,
                topic=row.topic,
                status=row.status,
                chunk_count=row.chunk_count,
                error_msg=row.error_msg,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def delete_document(self, user_id: str, doc_id: str) -> bool:
        """删除用户文档记录。"""
        with self._new_session() as session:
            row = (
                session.query(UserDocument)
                .filter_by(doc_id=doc_id, user_id=user_id)
                .first()
            )
            if row is None:
                return False
            session.delete(row)
            session.commit()
            logger.debug("Deleted document record: %s", doc_id)
            return True

    # ------------------------------------------------------------------ #
    # 知识卡片（技巧库）
    # ------------------------------------------------------------------ #
    def save_knowledge_card(self, card: KnowledgeCardData) -> KnowledgeCardData:
        """保存或更新知识卡片。"""
        with self._new_session() as session:
            existing = (
                session.query(KnowledgeCard)
                .filter_by(card_id=card.card_id, user_id=card.user_id)
                .first()
            ) if card.card_id else None
            if existing is None:
                row = KnowledgeCard(
                    card_id=card.card_id or uuid.uuid4().hex[:16],
                    user_id=card.user_id,
                    title=card.title,
                    content=card.content,
                    card_type=card.card_type,
                    tags=card.tags,
                    source_doc_id=card.source_doc_id,
                )
                session.add(row)
            else:
                existing.title = card.title
                existing.content = card.content
                existing.card_type = card.card_type
                existing.tags = card.tags
                existing.source_doc_id = card.source_doc_id
            session.commit()
            row = (
                session.query(KnowledgeCard)
                .filter_by(card_id=(row.card_id if existing is None else existing.card_id))
                .first()
            )
            return KnowledgeCardData(
                card_id=row.card_id,
                user_id=row.user_id,
                title=row.title,
                content=row.content,
                card_type=row.card_type,
                tags=row.tags,
                source_doc_id=row.source_doc_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def list_knowledge_cards(
        self, user_id: str, card_type: str | None = None, tag: str | None = None
    ) -> list[KnowledgeCardData]:
        """列出用户的知识卡片，支持按类型和标签过滤。"""
        with self._new_session() as session:
            query = session.query(KnowledgeCard).filter_by(user_id=user_id)
            if card_type:
                query = query.filter_by(card_type=card_type)
            if tag:
                # SQLite JSON 数组包含查询（简单实现）
                query = query.filter(KnowledgeCard.tags.like(f'%"{tag}"%'))
            rows = query.order_by(KnowledgeCard.created_at.desc()).all()
            return [
                KnowledgeCardData(
                    card_id=r.card_id,
                    user_id=r.user_id,
                    title=r.title,
                    content=r.content,
                    card_type=r.card_type,
                    tags=r.tags,
                    source_doc_id=r.source_doc_id,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]

    def get_knowledge_card(self, user_id: str, card_id: str) -> KnowledgeCardData | None:
        """获取单个知识卡片。"""
        with self._new_session() as session:
            row = (
                session.query(KnowledgeCard)
                .filter_by(card_id=card_id, user_id=user_id)
                .first()
            )
            if row is None:
                return None
            return KnowledgeCardData(
                card_id=row.card_id,
                user_id=row.user_id,
                title=row.title,
                content=row.content,
                card_type=row.card_type,
                tags=row.tags,
                source_doc_id=row.source_doc_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def delete_knowledge_card(self, user_id: str, card_id: str) -> bool:
        """删除知识卡片。"""
        with self._new_session() as session:
            row = (
                session.query(KnowledgeCard)
                .filter_by(card_id=card_id, user_id=user_id)
                .first()
            )
            if row is None:
                return False
            session.delete(row)
            session.commit()
            logger.debug("Deleted knowledge card: %s", card_id)
            return True

    # ------------------------------------------------------------------ #
    # 上下文构建
    # ------------------------------------------------------------------ #
    def build_user_context(
        self, user_id: str, max_conversations: int = 3
    ) -> UserContext:
        profile = self.get_or_create_user(user_id)
        recent_conversations = self.list_conversations(
            user_id, limit=max_conversations
        )
        recent_scripts = self.list_scripts(user_id)[:max_conversations]
        return UserContext(
            profile=profile,
            preferences=[],
            recent_conversations=recent_conversations,
            recent_scripts=recent_scripts,
        )

    # ------------------------------------------------------------------ #
    # Token 账户
    # ------------------------------------------------------------------ #
    def get_token_account(self, user_id: str) -> TokenAccountData | None:
        """获取用户 Token 账户，不存在则自动创建（赠 5000）。"""
        with self._new_session() as session:
            row = session.query(UserTokenAccount).filter_by(user_id=user_id).first()
            if row is None:
                row = UserTokenAccount(user_id=user_id, balance=5000, total_consumed=0, total_recharged=0)
                session.add(row)
                session.commit()
                logger.info("Created token account for user: %s", user_id)
            return TokenAccountData(
                user_id=row.user_id,
                balance=row.balance,
                total_consumed=row.total_consumed,
                total_recharged=row.total_recharged,
                updated_at=row.updated_at,
            )

    def deduct_tokens(self, user_id: str, amount: int) -> bool:
        """扣减用户 Token 余额。"""
        with self._new_session() as session:
            row = session.query(UserTokenAccount).filter_by(user_id=user_id).first()
            if row is None:
                row = UserTokenAccount(user_id=user_id, balance=5000, total_consumed=0, total_recharged=0)
                session.add(row)
            if row.balance < amount:
                return False
            row.balance -= amount
            row.total_consumed += amount
            row.updated_at = self._now()
            session.commit()
            logger.debug("Deducted %d tokens from %s, balance=%d", amount, user_id, row.balance)
            return True

    def recharge_tokens(self, user_id: str, amount: int) -> TokenAccountData:
        """充值用户 Token 余额。"""
        with self._new_session() as session:
            row = session.query(UserTokenAccount).filter_by(user_id=user_id).first()
            if row is None:
                row = UserTokenAccount(user_id=user_id, balance=5000, total_consumed=0, total_recharged=0)
                session.add(row)
            row.balance += amount
            row.total_recharged += amount
            row.updated_at = self._now()
            session.commit()
            logger.info("Recharged %d tokens for %s, balance=%d", amount, user_id, row.balance)
            return TokenAccountData(
                user_id=row.user_id,
                balance=row.balance,
                total_consumed=row.total_consumed,
                total_recharged=row.total_recharged,
                updated_at=row.updated_at,
            )

    # ------------------------------------------------------------------ #
    # 项目
    # ------------------------------------------------------------------ #
    def save_project(self, user_id: str, project: ProjectData) -> ProjectData:
        project_id = project.project_id or uuid.uuid4().hex[:16]
        with self._new_session() as session:
            row = session.query(UserProject).filter_by(project_id=project_id, user_id=user_id).first()
            if row is None:
                row = UserProject(
                    project_id=project_id,
                    user_id=user_id,
                    name=project.name,
                    project_type=project.project_type,
                )
                session.add(row)
            else:
                row.name = project.name
                row.project_type = project.project_type
                row.updated_at = self._now()
            session.commit()
            logger.debug("Saved project: %s", project_id)
            return ProjectData(
                project_id=row.project_id,
                user_id=row.user_id,
                name=row.name,
                project_type=row.project_type,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def load_project(self, user_id: str, project_id: str) -> ProjectData | None:
        with self._new_session() as session:
            row = session.query(UserProject).filter_by(project_id=project_id, user_id=user_id).first()
            if row is None:
                return None
            return ProjectData(
                project_id=row.project_id,
                user_id=row.user_id,
                name=row.name,
                project_type=row.project_type,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def list_projects(self, user_id: str) -> list[ProjectData]:
        with self._new_session() as session:
            rows = (
                session.query(UserProject)
                .filter_by(user_id=user_id)
                .order_by(UserProject.updated_at.desc())
                .all()
            )
            return [
                ProjectData(
                    project_id=r.project_id,
                    user_id=r.user_id,
                    name=r.name,
                    project_type=r.project_type,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]

    def delete_project(self, user_id: str, project_id: str) -> bool:
        with self._new_session() as session:
            row = session.query(UserProject).filter_by(project_id=project_id, user_id=user_id).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            logger.debug("Deleted project: %s", project_id)
            return True

    # ------------------------------------------------------------------ #
    # 加点盐历史
    # ------------------------------------------------------------------ #
    def save_salt_history(self, history: SaltHistoryData) -> SaltHistoryData:
        salt_id = history.salt_id or uuid.uuid4().hex[:16]
        with self._new_session() as session:
            row = SaltHistory(
                salt_id=salt_id,
                user_id=history.user_id,
                project_id=history.project_id,
                original_text=history.original_text,
                polished_text=history.polished_text,
                salt_level=history.salt_level,
                token_cost=history.token_cost,
            )
            session.add(row)
            session.commit()
            logger.debug("Saved salt history: %s", salt_id)
            return SaltHistoryData(
                salt_id=row.salt_id,
                user_id=row.user_id,
                project_id=row.project_id,
                original_text=row.original_text,
                polished_text=row.polished_text,
                salt_level=row.salt_level,
                token_cost=row.token_cost,
                created_at=row.created_at,
            )

    def list_salt_history(self, user_id: str, project_id: str | None = None) -> list[SaltHistoryData]:
        with self._new_session() as session:
            query = session.query(SaltHistory).filter_by(user_id=user_id)
            if project_id is not None:
                query = query.filter_by(project_id=project_id)
            rows = query.order_by(SaltHistory.created_at.desc()).all()
            return [
                SaltHistoryData(
                    salt_id=r.salt_id,
                    user_id=r.user_id,
                    project_id=r.project_id,
                    original_text=r.original_text,
                    polished_text=r.polished_text,
                    salt_level=r.salt_level,
                    token_cost=r.token_cost,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    # ------------------------------------------------------------------ #
    # IP 风格模型
    # ------------------------------------------------------------------ #
    def save_ip_style(self, style: IPStyleData) -> IPStyleData:
        style_id = style.style_id or uuid.uuid4().hex[:16]
        with self._new_session() as session:
            row = session.query(IPStyle).filter_by(style_id=style_id).first()
            if row is None:
                row = IPStyle(
                    style_id=style_id,
                    actor_name=style.actor_name,
                    version=style.version,
                    description=style.description,
                    prompt_snippet=style.prompt_snippet,
                    status=style.status,
                    split_ratio=style.split_ratio,
                    usage_count=style.usage_count,
                    avatar_url=style.avatar_url,
                    homepage_background=style.homepage_background,
                    profile_url=style.profile_url,
                    follower_count=style.follower_count or 0,
                    is_official=style.is_official if style.is_official is not None else False,
                    skill_id=style.skill_id,
                )
                session.add(row)
            else:
                row.actor_name = style.actor_name
                row.version = style.version
                row.description = style.description
                row.prompt_snippet = style.prompt_snippet
                row.status = style.status
                row.split_ratio = style.split_ratio
                row.usage_count = style.usage_count
                row.avatar_url = style.avatar_url
                row.homepage_background = style.homepage_background
                row.profile_url = style.profile_url
                row.follower_count = style.follower_count or 0
                row.is_official = style.is_official if style.is_official is not None else False
                row.skill_id = style.skill_id
                row.updated_at = self._now()
            session.commit()
            logger.debug("Saved IP style: %s", style_id)
            return IPStyleData(
                style_id=row.style_id,
                actor_name=row.actor_name,
                version=row.version,
                description=row.description,
                prompt_snippet=row.prompt_snippet,
                status=row.status,
                split_ratio=row.split_ratio,
                usage_count=row.usage_count,
                avatar_url=row.avatar_url,
                homepage_background=row.homepage_background,
                profile_url=row.profile_url,
                follower_count=row.follower_count,
                is_official=row.is_official,
                skill_id=row.skill_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def load_ip_style(self, style_id: str) -> IPStyleData | None:
        with self._new_session() as session:
            row = session.query(IPStyle).filter_by(style_id=style_id).first()
            if row is None:
                return None
            return IPStyleData(
                style_id=row.style_id,
                actor_name=row.actor_name,
                version=row.version,
                description=row.description,
                prompt_snippet=row.prompt_snippet,
                status=row.status,
                split_ratio=row.split_ratio,
                usage_count=row.usage_count,
                avatar_url=row.avatar_url,
                homepage_background=row.homepage_background,
                profile_url=row.profile_url,
                follower_count=row.follower_count,
                is_official=row.is_official,
                skill_id=row.skill_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def list_ip_styles(self, status: str | None = None) -> list[IPStyleData]:
        with self._new_session() as session:
            query = session.query(IPStyle)
            if status is not None:
                query = query.filter_by(status=status)
            rows = query.order_by(IPStyle.usage_count.desc()).all()
            return [
                IPStyleData(
                    style_id=r.style_id,
                    actor_name=r.actor_name,
                    version=r.version,
                    description=r.description,
                    prompt_snippet=r.prompt_snippet,
                    status=r.status,
                    split_ratio=r.split_ratio,
                    usage_count=r.usage_count,
                    avatar_url=r.avatar_url,
                    homepage_background=r.homepage_background,
                    profile_url=r.profile_url,
                    follower_count=r.follower_count,
                    is_official=r.is_official,
                    skill_id=r.skill_id,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]

    def delete_ip_style(self, style_id: str) -> bool:
        with self._new_session() as session:
            row = session.query(IPStyle).filter_by(style_id=style_id).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            logger.debug("Deleted IP style: %s", style_id)
            return True

    # ------------------------------------------------------------------ #
    # 投稿
    # ------------------------------------------------------------------ #
    def save_submission(self, submission: SubmissionData) -> SubmissionData:
        submission_id = submission.submission_id or uuid.uuid4().hex[:16]
        with self._new_session() as session:
            row = session.query(ScriptSubmission).filter_by(submission_id=submission_id).first()
            if row is None:
                row = ScriptSubmission(
                    submission_id=submission_id,
                    user_id=submission.user_id,
                    script_id=submission.script_id,
                    target_actor=submission.target_actor,
                    status=submission.status,
                    actor_comment=submission.actor_comment,
                )
                session.add(row)
            else:
                row.target_actor = submission.target_actor
                row.status = submission.status
                row.actor_comment = submission.actor_comment
                row.updated_at = self._now()
            session.commit()
            logger.debug("Saved submission: %s", submission_id)
            return SubmissionData(
                submission_id=row.submission_id,
                user_id=row.user_id,
                script_id=row.script_id,
                target_actor=row.target_actor,
                status=row.status,
                actor_comment=row.actor_comment,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def load_submission(self, submission_id: str) -> SubmissionData | None:
        with self._new_session() as session:
            row = session.query(ScriptSubmission).filter_by(submission_id=submission_id).first()
            if row is None:
                return None
            return SubmissionData(
                submission_id=row.submission_id,
                user_id=row.user_id,
                script_id=row.script_id,
                target_actor=row.target_actor,
                status=row.status,
                actor_comment=row.actor_comment,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def list_submissions(
        self, user_id: str | None = None, target_actor: str | None = None, status: str | None = None
    ) -> list[SubmissionData]:
        with self._new_session() as session:
            query = session.query(ScriptSubmission)
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            if target_actor is not None:
                query = query.filter_by(target_actor=target_actor)
            if status is not None:
                query = query.filter_by(status=status)
            rows = query.order_by(ScriptSubmission.created_at.desc()).all()
            return [
                SubmissionData(
                    submission_id=r.submission_id,
                    user_id=r.user_id,
                    script_id=r.script_id,
                    target_actor=r.target_actor,
                    status=r.status,
                    actor_comment=r.actor_comment,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]

    def review_submission(self, submission_id: str, status: str, comment: str | None = None) -> bool:
        with self._new_session() as session:
            row = session.query(ScriptSubmission).filter_by(submission_id=submission_id).first()
            if row is None:
                return False
            row.status = status
            row.actor_comment = comment
            row.updated_at = self._now()
            session.commit()
            logger.debug("Reviewed submission %s -> %s", submission_id, status)
            return True

    # ------------------------------------------------------------------ #
    # 收益记录
    # ------------------------------------------------------------------ #
    def save_earning(self, record: EarningRecordData) -> EarningRecordData:
        record_id = record.record_id or uuid.uuid4().hex[:16]
        with self._new_session() as session:
            row = EarningRecord(
                record_id=record_id,
                user_id=record.user_id,
                actor_name=record.actor_name,
                record_type=record.record_type,
                amount=record.amount,
                description=record.description,
            )
            session.add(row)
            session.commit()
            logger.debug("Saved earning record: %s", record_id)
            return EarningRecordData(
                record_id=row.record_id,
                user_id=row.user_id,
                actor_name=row.actor_name,
                record_type=row.record_type,
                amount=row.amount,
                description=row.description,
                created_at=row.created_at,
            )

    def list_earnings(self, user_id: str | None = None, actor_name: str | None = None) -> list[EarningRecordData]:
        with self._new_session() as session:
            query = session.query(EarningRecord)
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            if actor_name is not None:
                query = query.filter_by(actor_name=actor_name)
            rows = query.order_by(EarningRecord.created_at.desc()).all()
            return [
                EarningRecordData(
                    record_id=r.record_id,
                    user_id=r.user_id,
                    actor_name=r.actor_name,
                    record_type=r.record_type,
                    amount=r.amount,
                    description=r.description,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    # ------------------------------------------------------------------ #
    # 敏感词
    # ------------------------------------------------------------------ #
    def save_banned_word(self, word: BannedWordData) -> BannedWordData:
        with self._new_session() as session:
            existing = session.query(BannedWord).filter_by(word=word.word).first()
            if existing is not None:
                existing.category = word.category
                existing.added_by = word.added_by
                session.commit()
                row = existing
            else:
                row = BannedWord(
                    word=word.word,
                    category=word.category,
                    added_by=word.added_by,
                )
                session.add(row)
                session.commit()
            logger.debug("Saved banned word: %s", row.word)
            return BannedWordData(
                word_id=row.word_id,
                word=row.word,
                category=row.category,
                added_by=row.added_by,
                created_at=row.created_at,
            )

    def list_banned_words(self, category: str | None = None) -> list[BannedWordData]:
        with self._new_session() as session:
            query = session.query(BannedWord)
            if category is not None:
                query = query.filter_by(category=category)
            rows = query.order_by(BannedWord.created_at.desc()).all()
            return [
                BannedWordData(
                    word_id=r.word_id,
                    word=r.word,
                    category=r.category,
                    added_by=r.added_by,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    def delete_banned_word(self, word_id: int) -> bool:
        with self._new_session() as session:
            row = session.query(BannedWord).filter_by(word_id=word_id).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            logger.debug("Deleted banned word: %d", word_id)
            return True

    # ------------------------------------------------------------------ #
    # 统计
    # ------------------------------------------------------------------ #
    def get_user_stats(self, user_id: str) -> dict[str, Any]:
        with self._new_session() as session:
            from sqlalchemy import func
            # 按 source 统计 conversation 数量
            rows = (
                session.query(UserConversation.source, func.count(UserConversation.session_id))
                .filter_by(user_id=user_id)
                .group_by(UserConversation.source)
                .all()
            )
            stats = {"generations": 0, "actor_usage": 0, "salt_usage": 0, "earnings": 0}
            for source, count in rows:
                if source == "chat":
                    stats["generations"] = count
                elif source == "actor":
                    stats["actor_usage"] = count
                elif source == "salt":
                    stats["salt_usage"] = count
            # 统计收益
            earnings_rows = session.query(EarningRecord).filter_by(user_id=user_id).all()
            stats["earnings"] = sum(r.amount for r in earnings_rows)
            return stats
