"""中期记忆 SQL 实现 —— SQLMemoryStore。

基于 SQLAlchemy + SQLite，实现 MemoryStore 抽象基类的全部接口。
支持用户画像、偏好、会话、作品的完整 CRUD。
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
    ConversationData,
    PreferenceItem,
    ScriptData,
    UserContext,
    UserProfileData,
)
from comedy_agent.memory.schema import (
    Base,
    UserConversation,
    UserPreference,
    UserProfile,
    UserScript,
)
from comedy_agent.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class SQLMemoryStore(MemoryStore):
    """基于 SQLite 的记忆存储实现。

    覆盖短期记忆（会话）与中期记忆（偏好、作品）的全部操作。
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
        Base.metadata.create_all(self.engine)
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

    # ------------------------------------------------------------------ #
    # 短期记忆 —— 会话
    # ------------------------------------------------------------------ #
    def save_conversation(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        summary: str | None = None,
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
                    expires_at=self._now() + timedelta(hours=24),
                )
                session.add(conv)
            else:
                conv.messages = messages
                conv.summary = summary
                conv.updated_at = self._now()
            session.commit()
            logger.debug("Saved conversation: %s", session_id)

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
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        expires_at=row.expires_at,
                    )
                )
            return results

    # ------------------------------------------------------------------ #
    # 中期记忆 —— 偏好
    # ------------------------------------------------------------------ #
    def save_preference(self, user_id: str, key: str, value: Any) -> None:
        with self._new_session() as session:
            pref = (
                session.query(UserPreference)
                .filter_by(user_id=user_id, key=key)
                .first()
            )
            if pref is None:
                pref = UserPreference(user_id=user_id, key=key, value=value)
                session.add(pref)
            else:
                pref.value = value
                pref.updated_at = self._now()
            session.commit()
            logger.debug("Saved preference: %s/%s", user_id, key)

    def load_preference(self, user_id: str, key: str) -> Any | None:
        with self._new_session() as session:
            pref = (
                session.query(UserPreference)
                .filter_by(user_id=user_id, key=key)
                .first()
            )
            return pref.value if pref else None

    def list_preferences(self, user_id: str) -> list[PreferenceItem]:
        with self._new_session() as session:
            rows = (
                session.query(UserPreference)
                .filter_by(user_id=user_id)
                .order_by(UserPreference.updated_at.desc())
                .all()
            )
            return [PreferenceItem(key=r.key, value=r.value) for r in rows]

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
        self, user_id: str, script_type: str | None = None
    ) -> list[ScriptData]:
        with self._new_session() as session:
            query = session.query(UserScript).filter_by(user_id=user_id)
            if script_type:
                query = query.filter_by(script_type=script_type)
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
    # 上下文构建
    # ------------------------------------------------------------------ #
    def build_user_context(
        self, user_id: str, max_conversations: int = 3
    ) -> UserContext:
        profile = self.get_or_create_user(user_id)
        preferences = self.list_preferences(user_id)
        recent_conversations = self.list_conversations(
            user_id, limit=max_conversations
        )
        recent_scripts = self.list_scripts(user_id)[:max_conversations]
        return UserContext(
            profile=profile,
            preferences=preferences,
            recent_conversations=recent_conversations,
            recent_scripts=recent_scripts,
        )
