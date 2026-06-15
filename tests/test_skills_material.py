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


def test_search_duckduckgo_success(skill: MaterialSkill) -> None:
    mock_results = [
        {"title": "标题1", "href": "https://example.com/1", "body": "摘要1"},
        {"title": "标题2", "href": "https://example.com/2", "body": "摘要2"},
    ]
    with patch.object(skill, "_search_duckduckgo", return_value=mock_results):
        results = skill._search("query", count=2)
    assert len(results) == 2
    assert results[0]["title"] == "标题1"


def test_search_fallback_to_searxng(skill: MaterialSkill) -> None:
    mock_searxng = [{"title": "SearXNG", "href": "https://searxng.example", "body": "结果"}]
    with (
        patch.object(skill, "_search_duckduckgo", return_value=[]),
        patch(
            "comedy_agent.skills.material.settings.searxng_url", "https://searxng.example"
        ),
        patch.object(skill, "_search_searxng", return_value=mock_searxng),
    ):
        results = skill._search("query", count=1)
    assert len(results) == 1
    assert results[0]["title"] == "SearXNG"


def test_search_fallback_to_bing(skill: MaterialSkill) -> None:
    mock_bing = [{"title": "Bing", "href": "https://bing.com", "body": "结果"}]
    with (
        patch.object(skill, "_search_duckduckgo", return_value=[]),
        patch(
            "comedy_agent.skills.material.settings.bing_search_api_key", "test-key"
        ),
        patch.object(skill, "_search_bing", return_value=mock_bing),
    ):
        results = skill._search("query", count=1)
    assert len(results) == 1
    assert results[0]["title"] == "Bing"


def test_search_fallback_to_tavily(skill: MaterialSkill) -> None:
    mock_tavily = [{"title": "Tavily", "href": "https://tavily.com", "body": "结果"}]
    with (
        patch.object(skill, "_search_duckduckgo", return_value=[]),
        patch(
            "comedy_agent.skills.material.settings.bing_search_api_key", ""
        ),
        patch(
            "comedy_agent.skills.material.settings.tavily_api_key", "test-key"
        ),
        patch.object(skill, "_search_tavily", return_value=mock_tavily),
    ):
        results = skill._search("query", count=1)
    assert len(results) == 1
    assert results[0]["title"] == "Tavily"


def test_search_bing_parses_json(skill: MaterialSkill) -> None:
    import json

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "webPages": {
                "value": [
                    {"name": "标题1", "url": "https://example.com/1", "snippet": "摘要1"},
                    {"name": "标题2", "url": "https://example.com/2", "snippet": "摘要2"},
                ]
            }
        }
    ).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_response):
        results = skill._search_bing("query", 2, "test-key")
    assert len(results) == 2
    assert results[0]["title"] == "标题1"
    assert results[0]["href"] == "https://example.com/1"


def test_search_forced_engine_skips_fallback_chain(skill: MaterialSkill) -> None:
    """配置 MATERIAL_SEARCH_ENGINE=bing 时只调用 Bing，不走 DuckDuckGo。"""
    mock_bing = [{"title": "Bing Only", "href": "https://bing.com", "body": "结果"}]
    with (
        patch(
            "comedy_agent.skills.material.settings.material_search_engine", "bing"
        ),
        patch(
            "comedy_agent.skills.material.settings.bing_search_api_key", "test-key"
        ),
        patch.object(skill, "_search_duckduckgo") as mock_ddgs,
        patch.object(skill, "_search_bing", return_value=mock_bing) as mock_bing,
    ):
        results = skill._search("query", count=1)
    assert len(results) == 1
    assert results[0]["title"] == "Bing Only"
    mock_ddgs.assert_not_called()
    mock_bing.assert_called_once_with("query", 1, "test-key")


def test_search_newsapi_parses_json(skill: MaterialSkill) -> None:
    import json

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "status": "ok",
            "articles": [
                {"title": "新闻1", "url": "https://example.com/1", "description": "摘要1"},
                {"title": "新闻2", "url": "https://example.com/2", "description": "摘要2"},
            ],
        }
    ).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_response):
        results = skill._search_newsapi("query", 2, "test-key")
    assert len(results) == 2
    assert results[0]["title"] == "新闻1"
    assert results[0]["href"] == "https://example.com/1"


def test_search_rss_parses_feed(skill: MaterialSkill) -> None:
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
        results = skill._search_rss("新闻", 2)
    assert len(results) == 2
    assert results[0]["title"] == "新闻1"


def test_search_searxng_parses_json(skill: MaterialSkill) -> None:
    import json
    from unittest.mock import patch

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "results": [
                {"title": "标题1", "url": "https://example.com/1", "content": "摘要1"},
                {"title": "标题2", "url": "https://example.com/2", "content": "摘要2"},
            ]
        }
    ).encode("utf-8")
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_response):
        results = skill._search_searxng("query", 2, "https://searxng.example")
    assert len(results) == 2
    assert results[0]["title"] == "标题1"
    assert results[0]["href"] == "https://example.com/1"


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
