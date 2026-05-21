"""测试 UnifiedMemory 统一接口。

覆盖上下文文本生成、Token 预算控制、透传接口。
"""

from __future__ import annotations

import pytest

from comedy_agent.memory.models import ScriptData
from comedy_agent.memory.unified import UnifiedMemory


@pytest.fixture
def memory() -> UnifiedMemory:
    """内存数据库实例。"""
    return UnifiedMemory(db_url="sqlite:///:memory:")


class TestUnifiedMemoryPassthrough:
    """透传接口测试。"""

    def test_user_crud(self, memory: UnifiedMemory) -> None:
        profile = memory.get_or_create_user("u100", nickname="Alice")
        assert profile.user_id == "u100"
        assert profile.nickname == "Alice"

    def test_preference_crud(self, memory: UnifiedMemory) -> None:
        memory.get_or_create_user("u101")
        memory.save_preference("u101", "style", "satire")
        assert memory.load_preference("u101", "style") == "satire"

    def test_script_crud(self, memory: UnifiedMemory) -> None:
        memory.get_or_create_user("u102")
        saved = memory.save_script(
            "u102", ScriptData(title="Test", content="hello")
        )
        loaded = memory.load_script(saved.script_id)
        assert loaded is not None
        assert loaded.title == "Test"

    def test_clean_expired_conversations(self, memory: UnifiedMemory) -> None:
        memory.get_or_create_user("u103")
        from comedy_agent.memory.schema import UserConversation
        from datetime import datetime, timedelta

        with memory._store._new_session() as session:
            session.add(
                UserConversation(
                    session_id="s_exp",
                    user_id="u103",
                    messages=[],
                    expires_at=datetime.utcnow() - timedelta(hours=1),
                )
            )
            session.commit()

        deleted = memory.clean_expired_conversations(user_id="u103")
        assert deleted == 1
        assert memory.load_conversation("u103", "s_exp") is None


class TestBuildContextText:
    """上下文文本生成测试。"""

    def test_empty_context(self, memory: UnifiedMemory) -> None:
        memory.get_or_create_user("u200")
        text = memory.build_context_text("u200")
        assert text == ""

    def test_with_preferences(self, memory: UnifiedMemory) -> None:
        memory.get_or_create_user("u201")
        memory.save_preference("u201", "style", "black_humor")
        memory.save_preference("u201", "disliked_tropes", ["pun"])

        text = memory.build_context_text("u201")
        assert "【用户偏好】" in text
        assert "style" in text
        assert "black_humor" in text
        assert "disliked_tropes" in text

    def test_with_conversations(self, memory: UnifiedMemory) -> None:
        memory.get_or_create_user("u202")
        memory.save_conversation(
            "u202",
            "s200",
            [{"role": "human", "content": "写一个职场段子"}],
            summary="用户请求职场主题脱口秀",
        )

        text = memory.build_context_text("u202")
        assert "【近期会话摘要】" in text
        assert "职场主题脱口秀" in text

    def test_with_scripts(self, memory: UnifiedMemory) -> None:
        memory.get_or_create_user("u203")
        memory.save_script(
            "u203",
            ScriptData(
                title="《加班日记》",
                content="周一到周五...",
                script_type="standup",
                rating=4.5,
            ),
        )

        text = memory.build_context_text("u203")
        assert "【近期作品】" in text
        assert "《加班日记》" in text
        assert "standup" in text
        assert "4.5" in text

    def test_token_budget_truncation(self, memory: UnifiedMemory) -> None:
        """Token 超预算时应截断低优先级内容。"""
        memory.get_or_create_user("u204")
        # 大量偏好（高优先级，应保留）
        for i in range(20):
            memory.save_preference(f"u204", f"key_{i}", f"value_{i}_" * 50)

        # 大量作品（低优先级，应被截断）
        for i in range(10):
            memory.save_script(
                "u204",
                ScriptData(
                    title=f"Script {i}",
                    content="content " * 100,
                    script_type="standup",
                ),
            )

        text = memory.build_context_text("u204", max_tokens=200)
        # 应该包含偏好，但可能没有作品
        assert "【用户偏好】" in text
        # Token 预算控制应生效，不会出现空结果
        assert len(text) > 0
        # 若发生截断，应有提示
        if "【近期作品】" not in text:
            assert "省略" in text or "..." in text

    def test_disable_sections(self, memory: UnifiedMemory) -> None:
        memory.get_or_create_user("u205")
        memory.save_preference("u205", "style", "observational")
        memory.save_conversation(
            "u205", "s201", [{"role": "human", "content": "hi"}]
        )

        text = memory.build_context_text(
            "u205",
            include_preferences=False,
            include_recent_conversations=False,
        )
        assert text == ""

    def test_max_conversations_limit(self, memory: UnifiedMemory) -> None:
        memory.get_or_create_user("u206")
        for i in range(5):
            memory.save_conversation(
                "u206", f"s{i}", [{"role": "human", "content": str(i)}]
            )

        text = memory.build_context_text("u206", max_conversations=2)
        # 5 个会话，但 max_conversations=2，应只显示 2 个
        count = text.count("会话 s")
        assert count <= 2

    def test_max_scripts_limit(self, memory: UnifiedMemory) -> None:
        memory.get_or_create_user("u207")
        for i in range(5):
            memory.save_script(
                "u207", ScriptData(title=f"Script {i}", content="x")
            )

        text = memory.build_context_text("u207", max_scripts=2)
        count = text.count("Script ")
        assert count <= 2
