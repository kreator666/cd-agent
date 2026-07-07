"""搜索 Worker。

根据用户输入或知识缺口执行 DuckDuckGo 搜索，
将结果写入 ``state.search_results``。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.agents.schemas import SearchResult, SearchResultItem
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位搜索查询优化助手。请根据用户请求，生成一个适合用 DuckDuckGo 搜索的简短查询。

用户请求：{user_input}
当前话题：{topic}

只输出查询关键词（不超过 20 字），不要解释。"""

try:
    from langchain_community.tools import DuckDuckGoSearchRun
except ImportError:
    DuckDuckGoSearchRun = None  # type: ignore[misc, assignment]


class SearchAgent:
    """搜索 Agent。"""

    def __init__(self) -> None:
        self._search_tool = DuckDuckGoSearchRun() if DuckDuckGoSearchRun else None

    def run(self, state: ComedyState, llm: BaseChatModel | None = None) -> dict[str, Any]:
        """执行搜索并返回结果。

        Args:
            state: 当前图状态。
            llm: 可选的外部 LLM，用于生成/优化查询。

        Returns:
            包含 ``search_results`` 与 ``phase`` 的更新字典。
        """
        if llm is None:
            llm = ModelFactory.get_model(
                state.model, task_type="fast"
            )

        query = self._build_query(llm, state)
        results = self._search(query)

        output = self._format_output(query, results)
        logger.debug("search: query=%s, results=%d", query, len(results))

        # 将搜索结果同时写入 knowledge_context，供后续 GuideAgent / Planner / Writer 使用
        knowledge_items = [
            {
                "title": f"搜索：{query}",
                "category": "search",
                "content": item.snippet,
                "summary": item.snippet,
                "source": "duckduckgo",
            }
            for item in results
        ]

        return {
            "search_results": [r.model_dump() for r in results],
            "knowledge_context": knowledge_items,
            "output": output,
            "phase": "consulting",
            "response_type": "guide",
        }

    def _format_output(self, query: str, results: list[SearchResultItem]) -> str:
        """将搜索结果格式化为可读文本。"""
        if not results:
            return f"关于「{query}」没有找到相关搜索结果。"
        lines = [f"关于「{query}」的搜索结果："]
        for i, item in enumerate(results, 1):
            lines.append(f"{i}. {item.snippet}")
        return "\n".join(lines)

    def _build_query(self, llm: BaseChatModel, state: ComedyState) -> str:
        """生成搜索查询。"""
        topic = (state.analysis or {}).get("topic", "")
        user_input = state.user_input

        if not topic:
            return user_input[:40]

        try:
            response = llm.invoke([
                (
                    "human",
                    PROMPT.format(user_input=user_input, topic=topic),
                )
            ])
            query = str(getattr(response, "content", response)).strip()
            return query[:60] or user_input[:40]
        except Exception as e:
            logger.warning("搜索查询生成失败，使用原输入: %s", e)
            return user_input[:40]

    def _search(self, query: str) -> list[SearchResultItem]:
        """调用 DuckDuckGo 搜索。"""
        if self._search_tool is None:
            logger.warning("DuckDuckGoSearchRun 未安装，返回空结果")
            return []

        try:
            raw = self._search_tool.run(query)
        except Exception as e:
            logger.warning("DuckDuckGo 搜索失败: %s", e)
            return []

        return self._parse_raw_results(str(raw))

    @staticmethod
    def _parse_raw_results(raw: str) -> list[SearchResultItem]:
        """将 DuckDuckGo 返回的文本解析为结构化结果。

        DuckDuckGoSearchRun 默认返回一段聚合文本，这里按行简单拆分。
        """
        items: list[SearchResultItem] = []
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        for line in lines[:5]:
            items.append(SearchResultItem(snippet=line))
        return items
