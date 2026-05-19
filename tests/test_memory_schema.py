"""测试记忆库 ORM Schema。

验证四张核心表（UserProfile、UserPreference、UserConversation、UserScript）
的创建、关系、CRUD 基础行为。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comedy_agent.memory.schema import (
    Base,
    UserConversation,
    UserPreference,
    UserProfile,
    UserScript,
)


class TestMemorySchema:
    """ORM Schema 基础测试。"""

    @pytest.fixture
    def db_session(self):
        """内存 SQLite 会话，每个测试独立。"""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            yield session

    # ------------------------------------------------------------------ #
    # UserProfile
    # ------------------------------------------------------------------ #
    def test_create_user_profile(self, db_session: Session) -> None:
        """用户画像基础创建与查询。"""
        user = UserProfile(user_id="u001", nickname="Test User")
        db_session.add(user)
        db_session.commit()

        result = db_session.query(UserProfile).filter_by(user_id="u001").first()
        assert result is not None
        assert result.nickname == "Test User"
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_user_profile_without_nickname(self, db_session: Session) -> None:
        """允许无昵称创建用户。"""
        user = UserProfile(user_id="u002")
        db_session.add(user)
        db_session.commit()

        result = db_session.query(UserProfile).filter_by(user_id="u002").first()
        assert result is not None
        assert result.nickname is None

    # ------------------------------------------------------------------ #
    # UserPreference —— 关系 & JSON value
    # ------------------------------------------------------------------ #
    def test_user_preference_relationship(self, db_session: Session) -> None:
        """偏好与用户画像的关系。"""
        user = UserProfile(user_id="u003")
        db_session.add(user)
        db_session.commit()

        pref = UserPreference(
            user_id="u003",
            key="preferred_style",
            value={"style": "black_humor", "intensity": "high"},
        )
        db_session.add(pref)
        db_session.commit()

        result = db_session.query(UserProfile).filter_by(user_id="u003").first()
        assert result is not None
        assert len(result.preferences) == 1
        assert result.preferences[0].key == "preferred_style"
        assert result.preferences[0].value == {"style": "black_humor", "intensity": "high"}

    def test_user_preference_multiple_keys(self, db_session: Session) -> None:
        """一个用户可有多条偏好。"""
        user = UserProfile(user_id="u004")
        db_session.add(user)
        db_session.commit()

        db_session.add_all([
            UserPreference(user_id="u004", key="disliked_tropes", value=["pun", "dad_joke"]),
            UserPreference(user_id="u004", key="language", value="zh-CN"),
        ])
        db_session.commit()

        result = db_session.query(UserProfile).filter_by(user_id="u004").first()
        assert len(result.preferences) == 2

    def test_cascade_delete_user(self, db_session: Session) -> None:
        """删除用户时级联删除其偏好。"""
        user = UserProfile(user_id="u005")
        db_session.add(user)
        db_session.commit()

        pref = UserPreference(user_id="u005", key="test", value="v")
        db_session.add(pref)
        db_session.commit()

        db_session.delete(user)
        db_session.commit()

        assert db_session.query(UserPreference).filter_by(user_id="u005").first() is None

    # ------------------------------------------------------------------ #
    # UserConversation —— 短期记忆
    # ------------------------------------------------------------------ #
    def test_user_conversation_json_messages(self, db_session: Session) -> None:
        """会话消息 JSON 序列化。"""
        user = UserProfile(user_id="u006")
        db_session.add(user)
        db_session.commit()

        conv = UserConversation(
            session_id="s001",
            user_id="u006",
            messages=[
                {"role": "human", "content": "写一个关于加班的段子"},
                {"role": "ai", "content": "好的，这是一个关于加班的脱口秀..."},
            ],
            summary="用户请求职场加班主题脱口秀",
        )
        db_session.add(conv)
        db_session.commit()

        result = db_session.query(UserConversation).filter_by(session_id="s001").first()
        assert result is not None
        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "human"
        assert result.summary == "用户请求职场加班主题脱口秀"

    def test_user_conversation_expires_at(self, db_session: Session) -> None:
        """会话过期时间字段。"""
        user = UserProfile(user_id="u007")
        db_session.add(user)
        db_session.commit()

        expires = datetime.utcnow() + timedelta(hours=24)
        conv = UserConversation(
            session_id="s002",
            user_id="u007",
            messages=[],
            expires_at=expires,
        )
        db_session.add(conv)
        db_session.commit()

        result = db_session.query(UserConversation).filter_by(session_id="s002").first()
        assert result.expires_at == expires

    # ------------------------------------------------------------------ #
    # UserScript —— 作品库
    # ------------------------------------------------------------------ #
    def test_user_script_full_fields(self, db_session: Session) -> None:
        """作品完整字段读写。"""
        user = UserProfile(user_id="u008")
        db_session.add(user)
        db_session.commit()

        script = UserScript(
            script_id="sc001",
            user_id="u008",
            title="《加班日记》",
            content="周一到周五，我是公司的...",
            script_type="standup",
            rating=4.5,
            tags=["职场", "黑色幽默"],
        )
        db_session.add(script)
        db_session.commit()

        result = db_session.query(UserScript).filter_by(script_id="sc001").first()
        assert result is not None
        assert result.title == "《加班日记》"
        assert result.script_type == "standup"
        assert result.rating == 4.5
        assert result.tags == ["职场", "黑色幽默"]

    def test_user_script_auto_id(self, db_session: Session) -> None:
        """script_id 留空时自动生成。"""
        user = UserProfile(user_id="u009")
        db_session.add(user)
        db_session.commit()

        script = UserScript(
            user_id="u009",
            content="自动生成 ID 的段子",
        )
        db_session.add(script)
        db_session.commit()

        result = db_session.query(UserScript).filter_by(user_id="u009").first()
        assert result is not None
        assert result.script_id is not None
        assert len(result.script_id) > 0

    def test_user_script_cascade_delete(self, db_session: Session) -> None:
        """删除用户时级联删除其作品。"""
        user = UserProfile(user_id="u010")
        db_session.add(user)
        db_session.commit()

        script = UserScript(
            script_id="sc002",
            user_id="u010",
            content="test",
        )
        db_session.add(script)
        db_session.commit()

        db_session.delete(user)
        db_session.commit()

        assert db_session.query(UserScript).filter_by(script_id="sc002").first() is None
