"""测试 SQLMemoryStore 中期记忆存取接口。

覆盖用户画像、会话（短期记忆）、偏好、作品的完整 CRUD。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from comedy_agent.memory.medium_term import SQLMemoryStore
from comedy_agent.memory.models import ConversationData, PreferenceItem, ScriptData


@pytest.fixture
def store() -> SQLMemoryStore:
    """内存数据库实例，每个测试独立。"""
    return SQLMemoryStore(db_url="sqlite:///:memory:")


class TestUserProfile:
    """用户画像测试。"""

    def test_get_or_create_user_new(self, store: SQLMemoryStore) -> None:
        profile = store.get_or_create_user("u001", nickname="Alice")
        assert profile.user_id == "u001"
        assert profile.nickname == "Alice"

    def test_get_or_create_user_existing(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u002", nickname="Bob")
        profile = store.get_or_create_user("u002", nickname="Charlie")
        # 已存在用户不应被覆盖
        assert profile.nickname == "Bob"

    def test_get_or_create_user_without_nickname(self, store: SQLMemoryStore) -> None:
        profile = store.get_or_create_user("u003")
        assert profile.nickname is None


class TestConversationShortTerm:
    """短期记忆（会话）测试。"""

    def test_save_and_load_conversation(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u010")
        messages = [
            {"role": "human", "content": "hello"},
            {"role": "ai", "content": "hi"},
        ]
        store.save_conversation("u010", "s001", messages, summary="test")

        conv = store.load_conversation("u010", "s001")
        assert conv is not None
        assert conv.session_id == "s001"
        assert len(conv.messages) == 2
        assert conv.summary == "test"
        assert conv.expires_at is not None

    def test_load_nonexistent_conversation(self, store: SQLMemoryStore) -> None:
        assert store.load_conversation("u011", "s999") is None

    def test_update_conversation(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u012")
        store.save_conversation("u012", "s002", [{"role": "human", "content": "a"}])
        store.save_conversation(
            "u012", "s002", [{"role": "human", "content": "b"}]
        )

        conv = store.load_conversation("u012", "s002")
        assert conv is not None
        assert conv.messages[0]["content"] == "b"

    def test_list_conversations_order(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u013")
        store.save_conversation("u013", "s003", [{"role": "human", "content": "first"}])
        store.save_conversation("u013", "s004", [{"role": "human", "content": "second"}])

        convs = store.list_conversations("u013")
        assert len(convs) == 2
        # 按 updated_at 倒序
        assert convs[0].session_id == "s004"
        assert convs[1].session_id == "s003"

    def test_list_conversations_limit(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u014")
        for i in range(5):
            store.save_conversation(
                "u014", f"s{i:03d}", [{"role": "human", "content": str(i)}]
            )
        convs = store.list_conversations("u014", limit=3)
        assert len(convs) == 3

    def test_conversation_expired(self, store: SQLMemoryStore) -> None:
        """过期会话应被过滤。"""
        store.get_or_create_user("u015")
        # 直接构造过期记录（绕过 save_conversation 的自动 24h 过期）
        from comedy_agent.memory.schema import UserConversation

        with store._new_session() as session:
            conv = UserConversation(
                session_id="s005",
                user_id="u015",
                messages=[],
                expires_at=datetime.utcnow() - timedelta(hours=1),
            )
            session.add(conv)
            session.commit()

        assert store.load_conversation("u015", "s005") is None
        assert store.list_conversations("u015") == []


class TestPreferences:
    """用户偏好测试。"""

    def test_save_and_load_preference(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u020")
        store.save_preference("u020", "style", "black_humor")

        value = store.load_preference("u020", "style")
        assert value == "black_humor"

    def test_update_preference(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u021")
        store.save_preference("u021", "style", "observational")
        store.save_preference("u021", "style", "satire")

        value = store.load_preference("u021", "style")
        assert value == "satire"

    def test_load_nonexistent_preference(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u022")
        assert store.load_preference("u022", "nonexistent") is None

    def test_list_preferences(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u023")
        store.save_preference("u023", "style", "black_humor")
        store.save_preference("u023", "language", "zh-CN")
        store.save_preference("u023", "disliked", ["pun", "dad_joke"])

        prefs = store.list_preferences("u023")
        assert len(prefs) == 3
        keys = {p.key for p in prefs}
        assert keys == {"style", "language", "disliked"}

    def test_list_preferences_empty(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u024")
        assert store.list_preferences("u024") == []


class TestScripts:
    """用户创作作品测试。"""

    def test_save_and_load_script(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u030")
        script = ScriptData(
            title="Test Script",
            content="This is a test.",
            script_type="standup",
            rating=4.5,
            tags=["test"],
        )
        saved = store.save_script("u030", script)
        assert saved.script_id is not None

        loaded = store.load_script(saved.script_id)
        assert loaded is not None
        assert loaded.title == "Test Script"
        assert loaded.content == "This is a test."
        assert loaded.script_type == "standup"
        assert loaded.rating == 4.5
        assert loaded.tags == ["test"]

    def test_save_script_with_explicit_id(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u031")
        script = ScriptData(
            script_id="my-script-001",
            content="content",
        )
        saved = store.save_script("u031", script)
        assert saved.script_id == "my-script-001"

    def test_update_script(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u032")
        script = ScriptData(title="Old", content="old content")
        saved = store.save_script("u032", script)

        updated = ScriptData(
            script_id=saved.script_id,
            title="New",
            content="new content",
        )
        store.save_script("u032", updated)

        loaded = store.load_script(saved.script_id)
        assert loaded is not None
        assert loaded.title == "New"
        assert loaded.content == "new content"

    def test_list_scripts(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u033")
        store.save_script(
            "u033",
            ScriptData(title="A", content="a", script_type="standup"),
        )
        store.save_script(
            "u033",
            ScriptData(title="B", content="b", script_type="draft"),
        )
        store.save_script(
            "u033",
            ScriptData(title="C", content="c", script_type="standup"),
        )

        all_scripts = store.list_scripts("u033")
        assert len(all_scripts) == 3

        standup_only = store.list_scripts("u033", script_type="standup")
        assert len(standup_only) == 2

    def test_delete_script(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u034")
        saved = store.save_script(
            "u034", ScriptData(title="To Delete", content="x")
        )
        assert store.delete_script(saved.script_id) is True
        assert store.load_script(saved.script_id) is None
        assert store.delete_script(saved.script_id) is False

    def test_rate_script(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u035")
        saved = store.save_script(
            "u035", ScriptData(title="Rate Me", content="x")
        )
        assert store.rate_script(saved.script_id, 4.5) is True

        loaded = store.load_script(saved.script_id)
        assert loaded is not None
        assert loaded.rating == 4.5

    def test_rate_nonexistent_script(self, store: SQLMemoryStore) -> None:
        assert store.rate_script("nonexistent", 5.0) is False


class TestBuildUserContext:
    """上下文构建测试。"""

    def test_build_user_context_full(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u040", nickname="Test User")
        store.save_preference("u040", "style", "black_humor")
        store.save_conversation(
            "u040",
            "s100",
            [{"role": "human", "content": "hi"}],
            summary="greeting",
        )
        store.save_script(
            "u040",
            ScriptData(title="Script A", content="content a", script_type="standup"),
        )

        ctx = store.build_user_context("u040")
        assert ctx.profile is not None
        assert ctx.profile.nickname == "Test User"
        assert len(ctx.preferences) == 1
        assert len(ctx.recent_conversations) == 1
        assert len(ctx.recent_scripts) == 1

    def test_build_user_context_empty(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u041")
        ctx = store.build_user_context("u041")
        assert ctx.profile is not None
        assert ctx.preferences == []
        assert ctx.recent_conversations == []
        assert ctx.recent_scripts == []
