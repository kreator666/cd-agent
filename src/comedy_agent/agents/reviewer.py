"""审核 Worker。

评估当前段落质量，给出通过/修改/重写建议。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.agents.schemas import ReviewDecision, ReviewResult
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位喜剧编辑。请审核以下脱口秀段落，给出修改建议。

用户请求：{user_input}
当前段落：
{section_text}

请严格输出 JSON 格式（不要 markdown 列表，不要额外解释）：
{{
  "decision": "通过 | 修改 | 重写",
  "comments": "具体修改建议，1-3 条",
  "score": 8
}}

只输出 JSON，不要任何其他内容。"""


class ReviewerAgent:
    """审核 Agent。"""

    def run(self, state: ComedyState, llm: BaseChatModel | None = None) -> dict[str, Any]:
        """审核当前段落。

        Args:
            state: 当前图状态。
            llm: 可选的外部 LLM。

        Returns:
            包含 ``review`` 与 ``phase`` 的更新字典。
        """
        if llm is None:
            llm = ModelFactory.get_model(
                state.model, task_type="analytical"
            )

        sections = state.sections
        if not sections or state.current_section >= len(sections):
            return {
                "review": {
                    "decision": ReviewDecision.APPROVE.value,
                    "comments": "",
                    "score": 7,
                },
                "phase": "human_review",
            }

        section_text = sections[state.current_section]
        prompt = PROMPT.format(
            user_input=state.user_input,
            section_text=section_text,
        )

        try:
            structured_llm = llm.with_structured_output(ReviewResult)
            result: ReviewResult = structured_llm.invoke([("human", prompt)])
        except Exception as e:
            logger.warning("审核结构化输出失败，使用文本兜底: %s", e)
            result = self._text_fallback(llm, prompt)

        logger.debug("reviewer: %s", result.model_dump())
        return {
            "review": result.model_dump(),
            "phase": "human_review",
        }

    def _text_fallback(self, llm: BaseChatModel, prompt: str) -> ReviewResult:
        """结构化输出失败时的文本兜底。"""
        import json
        import re

        response = llm.invoke([("human", prompt)])
        content = str(getattr(response, "content", response))

        code_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
        if code_match:
            content = code_match.group(1).strip()

        # 1. 先尝试按 JSON 解析
        try:
            data = json.loads(content)
            return ReviewResult(**data)
        except Exception:
            pass

        # 2. 再尝试解析 markdown 列表 / key-value 形式
        def _extract(pattern: str, default: str = "") -> str:
            m = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            return m.group(1).strip() if m else default

        decision_text = _extract(r"[-*]\s*decision[:：]\s*(.+?)(?:\n|$)")
        comments_text = _extract(r"[-*]\s*comments[:：]\s*(.+?)(?:\n[-*]|$)")
        score_text = _extract(r"[-*]\s*score[:：]\s*(\d+)")

        lowered = (decision_text or content).lower()
        if "通过" in lowered:
            decision = ReviewDecision.APPROVE
        elif "重写" in lowered:
            decision = ReviewDecision.REWRITE
        else:
            decision = ReviewDecision.MODIFY

        score = 5
        if score_text:
            try:
                score = max(1, min(10, int(score_text)))
            except ValueError:
                pass

        comments = comments_text or content[:200]
        return ReviewResult(decision=decision, comments=comments, score=score)
