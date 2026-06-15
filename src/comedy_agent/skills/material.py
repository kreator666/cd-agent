"""素材搜索 Skill —— 根据用户输入和话题搜索外部网络资料。"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from comedy_agent.core.config import settings
from comedy_agent.models.factory import ModelFactory
from comedy_agent.skills.base import ComedySkill

logger = logging.getLogger(__name__)

# 可选依赖：DuckDuckGo 搜索（主搜索）
try:
    from duckduckgo_search import DDGS

    _HAS_DDGS = True
except ImportError:  # pragma: no cover
    _HAS_DDGS = False
    logger.warning("duckduckgo-search 未安装，素材搜索将不可用")

# 可选依赖：Tavily 搜索（备选）
try:
    from tavily import TavilyClient

    _HAS_TAVILY = True
except ImportError:  # pragma: no cover
    _HAS_TAVILY = False


class MaterialArgs(BaseModel):
    """素材搜索参数 Schema。"""

    query: str = Field(description="搜索关键词")
    topic: str = Field(default="", description="当前创作话题，用于扩展搜索意图")
    count: int = Field(default=5, ge=1, le=10, description="返回结果数量（最大 10）")


class MaterialSkill(ComedySkill):
    """素材搜索器。

    根据用户输入的搜索词，结合当前创作话题，搜索外部网络资料并整理为创作参考。
    """

    task_type: str = "analytical"
    name: str = "material"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "素材搜索。根据用户输入结合当前话题，搜索外部网络资料并整理为创作参考。"
    )
    args_schema: type[BaseModel] = MaterialArgs

    SYSTEM_PROMPT: str = (
        "你是一位资料整理助手。请将搜索到的网页资料整理成结构化的创作参考。\n"
        "每条素材需包含：标题、摘要、来源链接。\n"
        "摘要控制在 100 字以内，突出与创作相关的关键信息。\n"
        "只输出整理后的素材，不要额外解释。"
    )

    def _run(
        self,
        query: str,
        topic: str = "",
        count: int = 5,
        user_id: str | None = None,
    ) -> str:
        search_query = self._build_search_query(query, topic)
        results = self._search(search_query, count=count)
        if not results:
            return "未搜索到相关素材，请尝试更换关键词。"
        return self._format_results(results, query, topic, count)

    async def _arun(
        self,
        query: str,
        topic: str = "",
        count: int = 5,
        user_id: str | None = None,
    ) -> str:
        return self._run(query, topic=topic, count=count, user_id=user_id)

    @staticmethod
    def _build_search_query(query: str, topic: str) -> str:
        """组合搜索词和话题，生成最终查询。"""
        parts = [query.strip()]
        if topic and topic.strip():
            parts.append(topic.strip())
        return " ".join(parts)

    _SEARCH_ENGINES: ClassVar[tuple[str, ...]] = (
        "duckduckgo",
        "searxng",
        "bing",
        "tavily",
        "newsapi",
        "rss",
    )

    def _search(self, query: str, count: int) -> list[dict[str, Any]]:
        """执行搜索。

        若配置了 ``material_search_engine``，则只使用该引擎；
        否则按 DuckDuckGo -> SearXNG -> Bing -> Tavily -> NewsAPI -> RSS 顺序回退。
        """
        forced = (getattr(settings, "material_search_engine", "") or "").lower().strip()
        if forced:
            return self._search_with_engine(query, count, forced)

        for engine in self._SEARCH_ENGINES:
            results = self._search_with_engine(query, count, engine)
            if results:
                return results
        return []

    def _search_with_engine(
        self, query: str, count: int, engine: str
    ) -> list[dict[str, Any]]:
        """使用指定搜索引擎查询。"""
        if engine == "duckduckgo":
            return self._search_duckduckgo(query, count)
        if engine == "searxng":
            searxng_url = getattr(settings, "searxng_url", "") or ""
            if searxng_url:
                return self._search_searxng(query, count, searxng_url)
            return []
        if engine == "bing":
            bing_key = getattr(settings, "bing_search_api_key", "") or ""
            if bing_key:
                return self._search_bing(query, count, bing_key)
            return []
        if engine == "tavily":
            tavily_key = getattr(settings, "tavily_api_key", "") or ""
            if tavily_key:
                return self._search_tavily(query, count, tavily_key)
            return []
        if engine == "newsapi":
            newsapi_key = getattr(settings, "newsapi_api_key", "") or ""
            if newsapi_key:
                return self._search_newsapi(query, count, newsapi_key)
            return []
        if engine == "rss":
            return self._search_rss(query, count)
        logger.warning("未知搜索引擎: %s", engine)
        return []

    @staticmethod
    def _search_duckduckgo(query: str, count: int) -> list[dict[str, Any]]:
        """使用 DuckDuckGo 搜索。"""
        if not _HAS_DDGS:
            return []
        try:
            with DDGS() as ddgs:
                response = ddgs.text(query, max_results=count, region="cn-zh")
                return [
                    {
                        "title": item.get("title", ""),
                        "href": item.get("href", ""),
                        "body": item.get("body", ""),
                    }
                    for item in response
                    if item.get("title") or item.get("body")
                ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("DuckDuckGo 搜索失败: %s", exc)
            return []

    @staticmethod
    def _search_searxng(query: str, count: int, base_url: str) -> list[dict[str, Any]]:
        """使用 SearXNG 搜索。"""
        try:
            url = base_url.rstrip("/") + "/search"
            params = {
                "q": query,
                "format": "json",
                "language": "zh-CN",
            }
            url = f"{url}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            return [
                {
                    "title": item.get("title", ""),
                    "href": item.get("url", ""),
                    "body": item.get("content", ""),
                }
                for item in data.get("results", [])
                if item.get("title") or item.get("content")
            ][:count]
        except Exception as exc:  # noqa: BLE001
            logger.warning("SearXNG 搜索失败: %s", exc)
            return []

    @staticmethod
    def _search_bing(query: str, count: int, api_key: str) -> list[dict[str, Any]]:
        """使用 Bing Web Search API 搜索。"""
        try:
            endpoint = getattr(settings, "bing_search_endpoint", "https://api.bing.microsoft.com/v7.0/search")
            params = {"q": query, "count": min(count, 50), "mkt": "zh-CN"}
            url = f"{endpoint}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(
                url,
                headers={
                    "Ocp-Apim-Subscription-Key": api_key,
                    "User-Agent": "comedy-agent/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            return [
                {
                    "title": item.get("name", ""),
                    "href": item.get("url", ""),
                    "body": item.get("snippet", ""),
                }
                for item in data.get("webPages", {}).get("value", [])
                if item.get("name") or item.get("snippet")
            ][:count]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bing 搜索失败: %s", exc)
            return []

    @staticmethod
    def _search_tavily(query: str, count: int, api_key: str) -> list[dict[str, Any]]:
        """使用 Tavily 搜索。"""
        if not _HAS_TAVILY:
            return []
        try:
            client = TavilyClient(api_key=api_key)
            response = client.search(query=query, max_results=count)
            return [
                {
                    "title": item.get("title", ""),
                    "href": item.get("url", ""),
                    "body": item.get("content", ""),
                }
                for item in response.get("results", [])
                if item.get("title") or item.get("content")
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tavily 搜索失败: %s", exc)
            return []

    @staticmethod
    def _search_newsapi(query: str, count: int, api_key: str) -> list[dict[str, Any]]:
        """使用 NewsAPI 搜索新闻。"""
        try:
            params = {
                "q": query,
                "pageSize": min(count, 100),
                "language": "zh" if any("\u4e00" <= c <= "\u9fff" for c in query) else "en",
                "apiKey": api_key,
            }
            url = f"https://newsapi.org/v2/everything?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "comedy-agent/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("status") != "ok":
                logger.warning("NewsAPI 返回错误: %s", data.get("message"))
                return []

            return [
                {
                    "title": item.get("title", ""),
                    "href": item.get("url", ""),
                    "body": item.get("description", ""),
                }
                for item in data.get("articles", [])
                if item.get("title") or item.get("description")
            ][:count]
        except Exception as exc:  # noqa: BLE001
            logger.warning("NewsAPI 搜索失败: %s", exc)
            return []

    @staticmethod
    def _search_rss(query: str, count: int) -> list[dict[str, Any]]:
        """通过 RSS 订阅源聚合新闻素材。"""
        import xml.etree.ElementTree as ET

        feeds_str = getattr(settings, "news_rss_feeds", "") or ""
        feeds = [f.strip() for f in feeds_str.split(",") if f.strip()]
        if not feeds:
            return []

        results: list[dict[str, Any]] = []
        per_feed = max(1, count // len(feeds) + 1)
        query_lower = query.lower()

        for feed_url in feeds:
            try:
                req = urllib.request.Request(
                    feed_url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        )
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    xml_data = resp.read()

                root = ET.fromstring(xml_data)
                channel = root.find("channel") if root.tag == "rss" else root
                if channel is None:
                    continue

                for item in channel.findall("item"):
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    desc = (item.findtext("description") or "").strip()

                    # 简单相关性过滤：标题或摘要包含查询词
                    if query and query_lower not in (title + desc).lower():
                        continue

                    if title or desc:
                        results.append({
                            "title": title,
                            "href": link,
                            "body": desc,
                        })
                    if len(results) >= count:
                        return results
            except Exception as exc:  # noqa: BLE001
                logger.warning("RSS 源解析失败 %s: %s", feed_url, exc)
                continue

        return results

    def _format_results(
        self,
        results: list[dict[str, Any]],
        query: str,
        topic: str,
        count: int,
    ) -> str:
        """使用 LLM 整理搜索结果，或直接格式化（无模型时）。"""
        search_text = "\n\n".join(
            [
                f"[{i + 1}] {item.get('title', '无标题')}\n{item.get('body', '')}\n来源：{item.get('href', '')}"
                for i, item in enumerate(results)
            ]
        )

        try:
            llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
            messages = [
                ("system", self.SYSTEM_PROMPT),
                (
                    "human",
                    f"搜索词：{query}\n创作话题：{topic}\n\n请根据以下搜索结果整理 {count} 条创作参考素材：\n\n{search_text}",
                ),
            ]
            from langchain_core.prompts import ChatPromptTemplate

            prompt = ChatPromptTemplate.from_messages(messages)
            chain = prompt | llm
            result = chain.invoke({})
            if hasattr(result, "content"):
                return str(result.content)
            return str(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 整理素材失败，使用原始格式: %s", exc)
            return self._fallback_format(results)

    @staticmethod
    def _fallback_format(results: list[dict[str, Any]]) -> str:
        """无 LLM 时的兜底格式化。"""
        lines = ["📚 参考素材："]
        for i, item in enumerate(results, 1):
            title = item.get("title", "无标题")
            href = item.get("href", "")
            body = item.get("body", "")[:120]
            lines.append(f"{i}. **{title}**\n   {body}{'...' if len(item.get('body', '')) > 120 else ''}\n   来源：{href}")
        return "\n\n".join(lines)
