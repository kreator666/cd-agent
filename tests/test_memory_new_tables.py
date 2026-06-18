"""测试新增数据表（Token 账户、项目、加点盐、IP 风格、投稿、收益、敏感词）。"""

from __future__ import annotations

import pytest

from comedy_agent.memory.medium_term import SQLMemoryStore
from comedy_agent.memory.models import (
    BannedWordData,
    EarningRecordData,
    IPStyleData,
    ProjectData,
    SaltHistoryData,
    ScriptData,
    SubmissionData,
    TokenAccountData,
)


@pytest.fixture
def store() -> SQLMemoryStore:
    """内存数据库实例，每个测试独立。"""
    return SQLMemoryStore(db_url="sqlite:///:memory:")


class TestTokenAccount:
    """Token 账户测试。"""

    def test_auto_create_on_get(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u001")
        account = store.get_token_account("u001")
        assert account is not None
        assert account.balance == 5000
        assert account.total_consumed == 0
        assert account.total_recharged == 0

    def test_deduct_success(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u002")
        ok = store.deduct_tokens("u002", 100)
        assert ok is True
        account = store.get_token_account("u002")
        assert account.balance == 4900
        assert account.total_consumed == 100

    def test_deduct_insufficient(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u003")
        ok = store.deduct_tokens("u003", 6000)
        assert ok is False
        account = store.get_token_account("u003")
        assert account.balance == 5000

    def test_recharge(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u004")
        store.deduct_tokens("u004", 100)
        account = store.recharge_tokens("u004", 500)
        assert account.balance == 5400
        assert account.total_recharged == 500


class TestProject:
    """项目测试。"""

    def test_create_and_load(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u010")
        project = store.save_project("u010", ProjectData(user_id="u010", name="脱口秀专场"))
        assert project.project_id is not None
        loaded = store.load_project("u010", project.project_id)
        assert loaded is not None
        assert loaded.name == "脱口秀专场"

    def test_update(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u011")
        p = store.save_project("u011", ProjectData(user_id="u011", name="旧名称"))
        store.save_project("u011", ProjectData(project_id=p.project_id, user_id="u011", name="新名称"))
        loaded = store.load_project("u011", p.project_id)
        assert loaded is not None
        assert loaded.name == "新名称"

    def test_list_order(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u012")
        store.save_project("u012", ProjectData(user_id="u012", name="项目A"))
        store.save_project("u012", ProjectData(user_id="u012", name="项目B"))
        projects = store.list_projects("u012")
        assert len(projects) == 2
        assert projects[0].name == "项目B"

    def test_delete(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u013")
        p = store.save_project("u013", ProjectData(user_id="u013", name="待删除"))
        assert store.delete_project("u013", p.project_id) is True
        assert store.load_project("u013", p.project_id) is None


class TestSaltHistory:
    """加点盐历史测试。"""

    def test_save_and_list(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u020")
        record = store.save_salt_history(
            SaltHistoryData(
                user_id="u020",
                original_text="hello",
                polished_text="hello world",
                salt_level="medium",
                token_cost=20,
            )
        )
        assert record.salt_id is not None
        history = store.list_salt_history("u020")
        assert len(history) == 1
        assert history[0].salt_level == "medium"

    def test_list_by_project(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u021")
        p = store.save_project("u021", ProjectData(user_id="u021", name="项目"))
        store.save_salt_history(
            SaltHistoryData(user_id="u021", project_id=p.project_id, original_text="a", polished_text="b", salt_level="light")
        )
        store.save_salt_history(
            SaltHistoryData(user_id="u021", original_text="c", polished_text="d", salt_level="heavy")
        )
        assert len(store.list_salt_history("u021", project_id=p.project_id)) == 1
        assert len(store.list_salt_history("u021")) == 2


class TestIPStyle:
    """IP 风格模型测试。"""

    def test_crud(self, store: SQLMemoryStore) -> None:
        style = store.save_ip_style(
            IPStyleData(actor_name="呼兰", version="v2.1", description="知识梗密集", prompt_snippet="你是呼兰...")
        )
        assert style.style_id is not None
        loaded = store.load_ip_style(style.style_id)
        assert loaded is not None
        assert loaded.actor_name == "呼兰"
        assert loaded.status == "active"

        store.delete_ip_style(style.style_id)
        assert store.load_ip_style(style.style_id) is None

    def test_list_by_status(self, store: SQLMemoryStore) -> None:
        store.save_ip_style(IPStyleData(actor_name="呼兰", version="v1", description="d1", prompt_snippet="p1"))
        store.save_ip_style(IPStyleData(actor_name="鸟鸟", version="v1", description="d2", prompt_snippet="p2", status="testing"))
        active = store.list_ip_styles(status="active")
        testing = store.list_ip_styles(status="testing")
        assert len(active) == 1
        assert len(testing) == 1


class TestSubmission:
    """投稿测试。"""

    def test_create_and_review(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u030")
        script = store.save_script("u030", ScriptData(title="段子", content="内容"))
        sub = store.save_submission(
            SubmissionData(user_id="u030", script_id=script.script_id, target_actor="呼兰")
        )
        assert sub.submission_id is not None
        assert sub.status == "pending"

        store.review_submission(sub.submission_id, "adopted", comment="不错")
        loaded = store.load_submission(sub.submission_id)
        assert loaded is not None
        assert loaded.status == "adopted"
        assert loaded.actor_comment == "不错"

    def test_list_filter(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u031")
        script = store.save_script("u031", ScriptData(title="s", content="c"))
        store.save_submission(SubmissionData(user_id="u031", script_id=script.script_id, target_actor="呼兰"))
        store.save_submission(SubmissionData(user_id="u031", script_id=script.script_id, target_actor="鸟鸟"))
        assert len(store.list_submissions(target_actor="呼兰")) == 1
        assert len(store.list_submissions(user_id="u031")) == 2


class TestEarningRecord:
    """收益记录测试。"""

    def test_save_and_list(self, store: SQLMemoryStore) -> None:
        store.get_or_create_user("u040")
        record = store.save_earning(
            EarningRecordData(user_id="u040", actor_name="呼兰", record_type="actor_split", amount=1500)
        )
        assert record.record_id is not None
        earnings = store.list_earnings(user_id="u040")
        assert len(earnings) == 1
        assert earnings[0].amount == 1500

    def test_platform_earning_no_user(self, store: SQLMemoryStore) -> None:
        record = store.save_earning(
            EarningRecordData(record_type="platform_fee", amount=3000, description="平台服务费")
        )
        assert record.record_id is not None
        assert len(store.list_earnings()) == 1


class TestBannedWord:
    """敏感词测试。"""

    def test_save_and_list(self, store: SQLMemoryStore) -> None:
        word = store.save_banned_word(BannedWordData(word="竞品A", category="competitor", added_by="admin"))
        assert word.word_id is not None
        words = store.list_banned_words()
        assert len(words) == 1
        assert words[0].word == "竞品A"

    def test_delete(self, store: SQLMemoryStore) -> None:
        word = store.save_banned_word(BannedWordData(word="敏感词"))
        assert store.delete_banned_word(word.word_id) is True
        assert len(store.list_banned_words()) == 0
