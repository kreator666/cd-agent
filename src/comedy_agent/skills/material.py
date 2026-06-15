"""素材搜索 Skill —— 根据用户输入和话题从 RSS 新闻源与网络搜索获取创作素材。"""

from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from comedy_agent.core.config import settings
from comedy_agent.models.factory import ModelFactory
from comedy_agent.skills.base import ComedySkill

try:
    from langchain_community.tools import DuckDuckGoSearchRun
except ImportError:
    DuckDuckGoSearchRun = None  # type: ignore[misc, assignment]

try:
    import jieba
except ImportError:
    jieba = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# 过滤摘要时仅取前 N 个字符，避免综合快讯、长回答等正文尾部包含大量无关关键词
_DESC_FILTER_LEN: int = 500
# 传送给 LLM 整理时，单条摘要最大长度
_DESC_FORMAT_LEN: int = 800


class MaterialArgs(BaseModel):
    """素材搜索参数 Schema。"""

    query: str = Field(description="搜索关键词")
    topic: str = Field(default="", description="当前创作话题，用于扩展搜索意图")
    count: int = Field(default=5, ge=1, le=10, description="返回结果数量（最大 10）")


class MaterialSkill(ComedySkill):
    """素材搜索器。

    根据用户输入的搜索词，结合当前创作话题，从配置的 RSS 新闻源中
    拉取最新文章并整理为创作参考。
    """

    task_type: str = "analytical"
    name: str = "material"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "素材搜索。根据用户输入结合当前话题，从 RSS 新闻源获取创作参考素材。"
    )
    args_schema: type[BaseModel] = MaterialArgs

    SYSTEM_PROMPT: str = (
        "你是一位资料整理助手。请将搜索到的新闻资料整理成结构化的创作参考。\n"
        "每条素材需包含：标题、摘要、来源链接。\n"
        "摘要控制在 100 字以内，突出与创作相关的关键信息。\n"
        "只输出整理后的素材，不要额外解释。"
    )

    @staticmethod
    def _clean_query(query: str) -> str:
        """清洗 query，去除常见的技能指令前缀与多余空白。"""
        if not query:
            return query
        # 去除 "使用 material 技能。" / "用 material 技能。" / "使用 material 技能来" 等前缀
        cleaned = re.sub(
            r"^(?:使用|用)\s*\w+(?:\s*技能)?\s*(?:来|去)?\s*[。：:.]?\s*",
            "",
            query,
            flags=re.IGNORECASE,
        )
        # 去除 "文本：" / "Text:" / "搜索词：" / "创作话题：" 等前缀
        cleaned = re.sub(
            r"^\s*(?:文本|text|搜索词|query|关键词|创作话题|topic)\s*[：:]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        return cleaned.strip()

    def _run(
        self,
        query: str,
        topic: str = "",
        count: int = 5,
        user_id: str | None = None,
    ) -> str:
        query = self._clean_query(query)
        if not query:
            return "未搜索到相关素材，请尝试更换关键词或检查 RSS 源配置。"
        # 使用原始 query 过滤 RSS，避免 topic 拼接后导致匹配过严
        results = self._search(query, count=count)
        if not results:
            return "未搜索到相关素材，请尝试更换关键词或检查 RSS 源配置。"
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

    def _search(self, query: str, count: int) -> list[dict[str, Any]]:
        """从 RSS 新闻源拉取并筛选素材；RSS 不足时用 DuckDuckGo 搜索补充。"""
        results = self._search_rss(query, count)
        if len(results) >= count:
            return results

        # RSS 结果不足时，尝试网络搜索兜底
        web_results = self._search_web(query, count=count - len(results))
        results.extend(web_results)
        return results[:count]

    @staticmethod
    def _search_web(query: str, count: int) -> list[dict[str, Any]]:
        """通过 DuckDuckGo 网络搜索补充素材。"""
        if not count or DuckDuckGoSearchRun is None:
            return []

        try:
            search = DuckDuckGoSearchRun()
            raw = search.run(query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DuckDuckGo 搜索失败: %s", exc)
            return []

        if not raw or not raw.strip():
            return []

        # DuckDuckGo 返回的是一段纯文本摘要，按段落拆分后整理为条目
        results: list[dict[str, Any]] = []
        for para in raw.split("\n"):
            para = para.strip()
            if not para or len(para) < 20:
                continue
            # DuckDuckGo 已按 query 排序，直接取前 N 段非空文本即可
            results.append({
                "title": para[:80] + ("..." if len(para) > 80 else ""),
                "href": "",
                "body": para,
            })
            if len(results) >= count:
                break

        return results

    @staticmethod
    def _search_rss(query: str, count: int) -> list[dict[str, Any]]:
        """通过 RSS/Atom 订阅源聚合新闻素材。

        支持标准 RSS 2.0 与 Atom 1.0 格式，对配置错误、HTTP 异常、
        非 XML 响应、以及不标准标签做容错处理。
        """
        feeds_str = getattr(settings, "news_rss_feeds", "") or ""
        # 清理 URL：去除首尾空白，并移除 URL 中间可能因配置错误混入的空格
        feeds = []
        for raw in feeds_str.split(","):
            cleaned = "".join(raw.split())
            if cleaned:
                feeds.append(cleaned)
        if not feeds:
            logger.warning("未配置 RSS 新闻源")
            return []

        results: list[dict[str, Any]] = []
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
                        ),
                        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content_type = resp.headers.get("Content-Type", "").lower()
                    # 若服务器明确返回 HTML 错误页，则直接跳过，避免解析 HTML 时报错
                    if "text/html" in content_type and "xml" not in content_type:
                        logger.warning("RSS 源返回 HTML 页面，可能已失效或需要登录: %s", feed_url)
                        continue
                    data = resp.read()

                if not data.strip():
                    logger.warning("RSS 源返回空响应: %s", feed_url)
                    continue

                root = ET.fromstring(data)

                # 同时支持 RSS 2.0 与 Atom 1.0
                if root.tag == "rss":
                    entries = MaterialSkill._parse_rss_channel(root, query, query_lower)
                elif root.tag.endswith("feed"):
                    entries = MaterialSkill._parse_atom_feed(root, query, query_lower)
                else:
                    logger.warning("RSS 源格式未知 %s: 根标签 <%s>", feed_url, root.tag)
                    continue

                results.extend(entries)
                if len(results) >= count:
                    return results[:count]
            except urllib.error.HTTPError as exc:
                logger.warning("RSS 源请求失败 %s: HTTP %s", feed_url, exc.code)
                continue
            except urllib.error.URLError as exc:
                logger.warning("RSS 源 URL 错误 %s: %s", feed_url, exc.reason)
                continue
            except ET.ParseError as exc:
                logger.warning("RSS 源 XML 解析失败 %s: %s", feed_url, exc)
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("RSS 源解析失败 %s: %s", feed_url, exc)
                continue

        return results[:count]

    @staticmethod
    def _tokenize_query(query: str) -> list[str]:
        """对查询词分词。中文使用 jieba，英文/已有空格文本按空格拆分。

        过滤掉单字/过短词，避免"作"、"带"等宽泛字造成误召回。
        """
        if not query:
            return []
        query = query.strip()
        tokens: list[str] = []
        if jieba is not None:
            for t in jieba.cut(query):
                t = t.strip()
                if len(t) >= 2:
                    tokens.append(t)
        else:
            tokens = [t for t in query.lower().split() if len(t) >= 2]

        # 同时保留完整 query，便于短语匹配
        if query not in tokens:
            tokens.append(query)
        return tokens

    @staticmethod
    def _is_relevant(title: str, desc: str, query_lower: str) -> bool:
        """判断条目是否与查询词相关。

        策略：优先按标题匹配；标题不匹配时，仅按摘要前 DESC_FILTER_LEN
        个字符匹配，避免综合快讯、长回答正文尾部包含无关关键词导致误召回。
        """
        if not query_lower:
            return True
        terms = MaterialSkill._tokenize_query(query_lower)
        if not terms:
            return True

        title_lower = title.lower()
        if any(t in title_lower for t in terms):
            return True

        desc_head = desc[:_DESC_FILTER_LEN].lower()
        if any(t in desc_head for t in terms):
            return True

        return False

    @staticmethod
    def _parse_rss_channel(root: ET.Element, query: str, query_lower: str) -> list[dict[str, Any]]:
        """解析 RSS 2.0 channel 中的条目。"""
        entries: list[dict[str, Any]] = []
        channel = root.find("channel")
        if channel is None:
            return entries
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if query and not MaterialSkill._is_relevant(title, desc, query_lower):
                continue
            if title or desc:
                entries.append({"title": title, "href": link, "body": desc})
        return entries

    @staticmethod
    def _parse_atom_feed(root: ET.Element, query: str, query_lower: str) -> list[dict[str, Any]]:
        """解析 Atom 1.0 feed 中的条目。"""
        entries: list[dict[str, Any]] = []
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", "", ns)).strip()
            link_el = entry.find("atom:link[@href]", ns)
            link = link_el.get("href", "").strip() if link_el is not None else ""
            desc = (entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns)).strip()
            if query and not MaterialSkill._is_relevant(title, desc, query_lower):
                continue
            if title or desc:
                entries.append({"title": title, "href": link, "body": desc})
        return entries

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
                f"[{i + 1}] {item.get('title', '无标题')}\n{item.get('body', '')[:_DESC_FORMAT_LEN]}\n来源：{item.get('href', '')}"
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
