"""上下文分析 Worker。

对创作请求进行话题 / 态度 / 偏见 / 情绪四维度分析，
输出结构化结果供 Planner 使用。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.agents.schemas import AnalysisResult
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位喜剧创作分析助手。请对用户的创作请求进行四维度分析。

用户请求：{user_input}

请输出以下 JSON 对应结构：
- topic: 核心话题（10 字以内）
- attitude: 创作者对话题的态度，如讽刺/自嘲/观察/批判/温情
- bias: 可能存在的认知偏见或刻板印象，没有则写'无'
- emotion: 目标情绪基调，如愤怒/荒诞/尴尬/温暖/无奈

只输出结构化结果，不要解释。"""


class ContextAnalyzerAgent:
    """上下文分析 Agent。"""

    def run(self, state: ComedyState, llm: BaseChatModel | None = None) -> dict[str, Any]:
        """执行四维度分析。

        Args:
            state: 当前图状态。
            llm: 可选的外部 LLM。

        Returns:
            包含 ``analysis`` 与 ``phase`` 的更新字典。
        """
        if llm is None:
            llm = ModelFactory.get_model(
                state.model, task_type="analytical"
            )

        prompt = PROMPT.format(user_input=state.user_input)

        try:
            structured_llm = llm.with_structured_output(AnalysisResult)
            result: AnalysisResult = structured_llm.invoke([("human", prompt)])
        except Exception as e:
            logger.warning("上下文分析结构化输出失败，使用文本兜底: %s", e)
            result = self._text_fallback(llm, state.user_input)

        logger.debug("context_analyzer: %s", result.model_dump())
        return {
            "analysis": result.model_dump(),
            "phase": "planning",
        }

    def _text_fallback(self, llm: BaseChatModel, user_input: str) -> AnalysisResult:
        """结构化输出失败时，使用普通文本输出并做简单解析。"""
        import json
        import re

        response = llm.invoke([("human", PROMPT.format(user_input=user_input))])
        content = str(getattr(response, "content", response))

        code_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
        if code_match:
            content = code_match.group(1).strip()

        try:
            data = json.loads(content)
            return AnalysisResult(**data)
        except Exception:
            logger.warning("文本兜底解析失败，使用默认值")

        return AnalysisResult(
            topic="未识别",
            attitude="观察",
            bias="无",
            emotion="温暖",
        )
