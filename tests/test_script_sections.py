"""分段打磨测试 —— 段落解析/合并纯函数 + /eval 分段打磨端点。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from comedy_agent.api.server import app, state
from comedy_agent.services.script_sections import merge_sections, parse_sections


def _patched_create_engine(*args, **kwargs):
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


def _mock_skill():
    """构造一个用于测试的 mock Skill。"""
    skill = MagicMock()
    skill.name = "standup_focused"
    skill.invoke.return_value = "这是生成的段子"
    return skill


@pytest.fixture
def client():
    """提供 TestClient，memory 使用内存数据库，带认证。"""
    with patch(
        "comedy_agent.memory.medium_term.create_engine", side_effect=_patched_create_engine
    ), patch("comedy_agent.api.server.AgentOrchestrator") as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch.run.return_value = {"output": "mocked", "messages": []}
        mock_orch.tools = []  # 让 eval 路由回退到 load_single_skill
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore

        store = SQLMemoryStore(db_url="sqlite:///:memory:")
        state.memory = store
        state.orch = mock_orch

        store.get_or_create_user("test_user", "测试用户")
        store.get_token_account("test_user")
        from comedy_agent.auth.security import create_access_token

        token = create_access_token("test_user")

        with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
            yield c

        state.memory = None
        state.orch = None


LABELED_CONTENT = """【标题】
骨折康复指南
【开场 Hook】
上个月我把腿摔骨折了，医生说我这属于「主动休息」。
【第一段：建立世界观】
打石膏这一个月，我算是明白了，什么叫「身体按下暂停键，生活开了加速器」。
【收尾：炸裂 Call Back】
所以别问我恢复得怎么样，我已经在练习下一次怎么摔得更有喜剧感了。
"""

UNLABELED_CONTENT = """大家好，今天聊聊上班。

上班最大的谎言就是「马上就好」。

"""


class TestParseSections:
    """parse_sections 纯函数测试。"""

    def test_labeled_content(self):
        sections = parse_sections(LABELED_CONTENT)
        assert [s["index"] for s in sections] == [0, 1, 2, 3]
        assert [s["title"] for s in sections] == [
            "标题",
            "开场 Hook",
            "第一段：建立世界观",
            "收尾：炸裂 Call Back",
        ]
        assert all(s["has_label"] for s in sections)
        assert "主动休息" in sections[1]["text"]
        assert "喜剧感" in sections[3]["text"]

    def test_preamble_before_first_label(self):
        content = "写在前面的一段话\n\n【开场 Hook】\n大家好"
        sections = parse_sections(content)
        assert sections[0]["index"] == 0
        assert sections[0]["title"] == "标题"
        assert sections[0]["has_label"] is False
        assert sections[0]["text"] == "写在前面的一段话"
        assert sections[1]["title"] == "开场 Hook"
        assert sections[1]["has_label"] is True

    def test_label_line_with_surrounding_whitespace(self):
        content = "  【开场 Hook】  \n大家好"
        sections = parse_sections(content)
        assert len(sections) == 1
        assert sections[0]["title"] == "开场 Hook"
        assert sections[0]["text"] == "大家好"

    def test_book_title_marks_not_treated_as_label(self):
        content = (
            "我最近读了《百年孤独》，感触很深。\n"
            "【开场 Hook】\n书里说【别在意这个】，人生如梦\n大家好"
        )
        sections = parse_sections(content)
        assert len(sections) == 2
        assert sections[0]["title"] == "标题"
        assert "《百年孤独》" in sections[0]["text"]
        # 行内（非整行）的【...】不算段标题
        assert sections[1]["title"] == "开场 Hook"
        assert "【别在意这个】" in sections[1]["text"]

    def test_fallback_split_by_blank_lines(self):
        sections = parse_sections(UNLABELED_CONTENT)
        assert len(sections) == 2
        assert sections[0]["title"] == "第1段"
        assert sections[1]["title"] == "第2段"
        assert all(not s["has_label"] for s in sections)
        assert "大家好" in sections[0]["text"]
        assert "马上就好" in sections[1]["text"]

    def test_empty_content(self):
        assert parse_sections("") == []
        assert parse_sections("   \n\n  ") == []


class TestMergeSections:
    """merge_sections 纯函数测试。"""

    def test_merge_labeled_output(self):
        sections = parse_sections(LABELED_CONTENT)
        merged = merge_sections(sections)
        assert "【标题】\n骨折康复指南" in merged
        assert "【开场 Hook】" in merged

    def test_merge_fallback_without_labels(self):
        sections = parse_sections(UNLABELED_CONTENT)
        merged = merge_sections(sections)
        assert "【" not in merged

    def test_round_trip_labeled(self):
        original = parse_sections(LABELED_CONTENT)
        assert parse_sections(merge_sections(original)) == original

    def test_round_trip_fallback(self):
        original = parse_sections(UNLABELED_CONTENT)
        assert parse_sections(merge_sections(original)) == original

    def test_round_trip_with_preamble(self):
        content = "无标签前言\n\n【第一段】\n正文内容"
        original = parse_sections(content)
        assert parse_sections(merge_sections(original)) == original


def _create_result(client) -> str:
    """通过 API 创建一个评测会话并返回 result_id。"""
    with patch("comedy_agent.api.routers.eval.load_single_skill") as mock_load_skill:
        mock_load_skill.return_value = _mock_skill()
        res = client.post(
            "/eval/sessions",
            json={
                "skill_name": "standup_focused",
                "model": "deepseek-v3",
                "topic": "骨折",
                "attitude": "自嘲",
                "bias": "无",
                "emotion": "荒诞",
            },
        )
    assert res.status_code == 200, res.text
    session_id = res.json()["session_id"]
    detail = client.get(f"/eval/sessions/{session_id}")
    assert detail.status_code == 200, detail.text
    return detail.json()["results"][0]["id"]


class TestSectionEndpoints:
    """分段打磨端点测试。"""

    def test_get_sections(self, client):
        result_id = _create_result(client)
        res = client.put(
            f"/eval/results/{result_id}/content", json={"content": LABELED_CONTENT}
        )
        assert res.status_code == 200, res.text

        res = client.get(f"/eval/results/{result_id}/sections")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["result_id"] == result_id
        assert data["has_labels"] is True
        assert len(data["sections"]) == 4
        first = data["sections"][0]
        assert first["index"] == 0
        assert first["title"] == "标题"
        assert first["has_label"] is True
        assert "骨折康复指南" in first["text"]

    def test_get_sections_unlabeled(self, client):
        result_id = _create_result(client)
        client.put(
            f"/eval/results/{result_id}/content", json={"content": UNLABELED_CONTENT}
        )
        res = client.get(f"/eval/results/{result_id}/sections")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["has_labels"] is False
        assert [s["title"] for s in data["sections"]] == ["第1段", "第2段"]
        assert all(not s["has_label"] for s in data["sections"])

    def test_get_sections_not_found(self, client):
        res = client.get("/eval/results/notexist/sections")
        assert res.status_code == 404

    def test_put_content(self, client):
        result_id = _create_result(client)
        res = client.put(
            f"/eval/results/{result_id}/content", json={"content": LABELED_CONTENT}
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["result_id"] == result_id
        assert data["content"] == LABELED_CONTENT.strip()

        detail = client.get(f"/eval/results/{result_id}")
        assert detail.status_code == 200
        assert detail.json()["content"] == LABELED_CONTENT.strip()

    def test_put_content_empty(self, client):
        result_id = _create_result(client)
        res = client.put(f"/eval/results/{result_id}/content", json={"content": ""})
        assert res.status_code == 422
        res = client.put(f"/eval/results/{result_id}/content", json={"content": "   "})
        assert res.status_code == 422

    def test_put_content_not_found(self, client):
        res = client.put("/eval/results/notexist/content", json={"content": "abc"})
        assert res.status_code == 404

    def _mock_llm(self, text: str) -> MagicMock:
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content=text)
        return llm

    def test_polish_section(self, client):
        result_id = _create_result(client)
        client.put(
            f"/eval/results/{result_id}/content", json={"content": LABELED_CONTENT}
        )

        llm = self._mock_llm("润色后的开场白")
        with patch(
            "comedy_agent.api.routers.eval.ModelFactory.get_model", return_value=llm
        ) as mock_get_model:
            res = client.post(f"/eval/results/{result_id}/sections/1/polish")

        assert res.status_code == 200, res.text
        assert res.json()["text"] == "润色后的开场白"
        mock_get_model.assert_called_once_with("deepseek-v3", task_type="creative")
        # 提示词中包含上下文信息
        prompt = llm.invoke.call_args[0][0][1][1]
        assert "开场 Hook" in prompt
        assert "骨折" in prompt
        assert "标题" in prompt

    def test_regenerate_section(self, client):
        result_id = _create_result(client)
        client.put(
            f"/eval/results/{result_id}/content", json={"content": LABELED_CONTENT}
        )

        llm = self._mock_llm("全新生成的内容")
        with patch(
            "comedy_agent.api.routers.eval.ModelFactory.get_model", return_value=llm
        ):
            res = client.post(f"/eval/results/{result_id}/sections/2/regenerate")

        assert res.status_code == 200, res.text
        assert res.json()["text"] == "全新生成的内容"
        prompt = llm.invoke.call_args[0][0][1][1]
        assert "全新创作" in prompt

    def test_polish_index_out_of_range(self, client):
        result_id = _create_result(client)
        client.put(
            f"/eval/results/{result_id}/content", json={"content": LABELED_CONTENT}
        )
        res = client.post(f"/eval/results/{result_id}/sections/99/polish")
        assert res.status_code == 400

    def test_polish_not_found(self, client):
        res = client.post("/eval/results/notexist/sections/0/polish")
        assert res.status_code == 404
