"""上下文分析 Worker。

对创作请求进行话题 / 态度 / 偏见 / 情绪四维度分析，
输出结构化结果供 Planner 使用。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AnyMessage

from comedy_agent.agents.schemas import AnalysisResult
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位喜剧创作分析助手。请根据用户与创作助手的完整对话历史，提炼出四维度分析结果。

## 历史摘要（如没有则忽略）
{conversation_summary}

## 最近对话历史
{conversation_history}

## 已收集的槽位（可能为空）
{slots}

## 上一轮分析（如没有则忽略）
{previous_analysis}

## 最新用户输入
{user_input}

请综合以上信息，输出以下 JSON 对应结构：
- topic: 核心话题（10 字以内）
- attitude: 创作者对话题的态度，如讽刺/自嘲/观察/批判/温情
- bias: 可能存在的认知偏见或刻板印象，没有则写'无'
- emotion: 目标情绪基调，如愤怒/荒诞/尴尬/温暖/无奈

只输出结构化结果，不要解释。"""


def _format_history(
    messages: list[AnyMessage], max_turns: int = 8, summary: str | None = None
) -> str:
    """把消息链格式化为对话历史文本，可选注入长对话摘要。"""
    parts: list[str] = []
    if summary:
        parts.append(f"【历史摘要】\n{summary}")

    if not messages:
        if not parts:
            return "（无）"
        return "\n\n".join(parts)

    # 取最近 N 轮，每轮可能包含 human + ai
    recent = messages[-max_turns * 2:]
    lines = []
    for m in recent:
        role = getattr(m, "type", "unknown")
        content = str(getattr(m, "content", "")).strip()
        if not content:
            continue
        if role == "human":
            lines.append(f"用户：{content}")
        elif role == "ai":
            lines.append(f"助手：{content}")
        else:
            lines.append(f"{role}：{content}")
    if lines:
        parts.append("【最近对话】\n" + "\n".join(lines))

    return "\n\n".join(parts) if parts else "（无）"


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

        prompt = self._build_prompt(state)

        try:
            structured_llm = llm.with_structured_output(AnalysisResult)
            result: AnalysisResult = structured_llm.invoke([("human", prompt)])
        except Exception as e:
            logger.warning("上下文分析结构化输出失败，使用文本兜底: %s", e)
            result = self._text_fallback(llm, state)

        logger.debug("context_analyzer: %s", result.model_dump())
        return {
            "analysis": result.model_dump(),
            "phase": "planning",
        }

    def _build_prompt(self, state: ComedyState) -> str:
        """构造包含完整对话历史的分析 Prompt。"""
        slots = state.slots or {}
        previous = state.analysis or {}
        return PROMPT.format(
            conversation_summary=state.conversation_summary or "（无）",
            conversation_history=_format_history(state.messages),
            slots="\n".join(f"- {k}：{v}" for k, v in slots.items()) or "（无）",
            previous_analysis="\n".join(f"- {k}：{v}" for k, v in previous.items()) or "（无）",
            user_input=state.user_input,
        )

    def _text_fallback(self, llm: BaseChatModel, state: ComedyState) -> AnalysisResult:
        """结构化输出失败时，使用普通文本输出并做简单解析。"""
        import json
        import re

        response = llm.invoke([("human", self._build_prompt(state))])
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
