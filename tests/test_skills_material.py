"""素材搜索 Skill 测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.skills.material import MaterialSkill


@pytest.fixture
def skill() -> MaterialSkill:
    return MaterialSkill()


def test_build_search_query_with_topic(skill: MaterialSkill) -> None:
    assert skill._build_search_query("职场 PUA", "互联网大厂") == "职场 PUA 互联网大厂"


def test_build_search_query_without_topic(skill: MaterialSkill) -> None:
    assert skill._build_search_query("职场 PUA", "") == "职场 PUA"


def test_search_rss_filters_by_query(skill: MaterialSkill) -> None:
    """RSS 解析应按查询词过滤并返回相关条目。"""
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
        <item><title>新闻1</title><link>https://example.com/1</link><description>摘要1</description></item>
        <item><title>新闻2</title><link>https://example.com/2</link><description>摘要2</description></item>
        <item><title>其他</title><link>https://example.com/3</link><description>无关内容</description></item>
    </channel></rss>""".encode("utf-8")
    mock_response = MagicMock()
    mock_response.read.return_value = rss_xml
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    with (
        patch(
            "comedy_agent.skills.material.settings.news_rss_feeds", "https://example.com/rss"
        ),
        patch("urllib.request.urlopen", return_value=mock_response),
    ):
        results = skill._search("新闻", 2)
    assert len(results) == 2
    assert results[0]["title"] == "新闻1"


def test_search_rss_empty_feeds(skill: MaterialSkill) -> None:
    """未配置 RSS 源时应返回空列表。"""
    with patch("comedy_agent.skills.material.settings.news_rss_feeds", ""):
        results = skill._search("query", count=1)
    assert results == []


def test_fallback_format(skill: MaterialSkill) -> None:
    results = [
        {"title": "标题", "href": "https://example.com", "body": "这是一个很长的摘要" * 10},
    ]
    formatted = skill._fallback_format(results)
    assert "📚 参考素材：" in formatted
    assert "标题" in formatted
    assert "https://example.com" in formatted


def test_run_returns_formatted_result(skill: MaterialSkill) -> None:
    mock_results = [
        {"title": "标题1", "href": "https://example.com/1", "body": "摘要1"},
    ]
    with patch.object(skill, "_search", return_value=mock_results):
        result = skill._run(query="测试", topic="话题", count=1)
    assert isinstance(result, str)
    assert len(result) > 0


def test_run_no_results(skill: MaterialSkill) -> None:
    with patch.object(skill, "_search", return_value=[]):
        result = skill._run(query="测试", topic="话题", count=1)
    assert "未搜索到相关素材" in result


@pytest.mark.asyncio
async def test_arun_delegates_to_run(skill: MaterialSkill) -> None:
    with patch.object(skill, "_run", return_value="async result") as mock_run:
        result = await skill._arun(query="测试")
    assert result == "async result"
    mock_run.assert_called_once()
