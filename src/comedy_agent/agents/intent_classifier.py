"""意图分类 Worker。

将用户输入分类为 writing / control / search / feedback / chat 五类。
Phase 2 使用 LLM 结构化输出，并保留规则兜底。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.agents.schemas import IntentClassification, UserIntent
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位意图分类助手。请根据用户输入判断其意图。

可选意图：
- writing：用户想要创作喜剧内容（脱口秀、小品、相声、漫才、剧本等）。
- search：用户想要搜索资料、找素材、查信息。
- control：用户想要停止、结束、退出、重置、清空当前任务。
- feedback：用户在审阅阶段给出通过、修改、重写、继续等反馈。
- chat：普通闲聊或问候，没有明确创作/搜索/控制意图。

当前会话阶段：{phase}
用户输入：{user_input}

请输出意图、置信度（0-1）和一句话理由。"""

# 规则兜底关键词（在 LLM 不可用时使用）
_WRITING_KEYWORDS = (
    "写", "创作", "来一段", "写一段", "写个", "来个", "段子", "脱口秀",
    "小品", "相声", "漫才", "剧本", "关于", "话题",
)
_SEARCH_KEYWORDS = ("搜索", "查一下", "查", "找", "资料", "素材")
_CONTROL_KEYWORDS = ("停止", "结束", "退出", "重置", "清空")
_FEEDBACK_KEYWORDS = ("通过", "修改", "重写", "继续", "ok", "yes", "no")


class IntentClassifierAgent:
    """意图分类 Agent。"""

    def run(self, state: ComedyState, llm: BaseChatModel | None = None) -> dict[str, Any]:
        """分类用户意图并返回要更新的状态字段。

        Args:
            state: 当前图状态。
            llm: 可选的外部 LLM。为 None 时通过 ModelFactory 获取。

        Returns:
            包含 ``intent`` 和 ``phase`` 的更新字典。
        """
        if llm is None:
            llm = ModelFactory.get_model(
                state.model, task_type="analytical"
            )

        prompt = PROMPT.format(
            phase=state.phase,
            user_input=state.user_input,
        )
        try:
            structured_llm = llm.with_structured_output(IntentClassification)
            result: IntentClassification = structured_llm.invoke(
                [("human", prompt)]
            )
        except Exception as e:
            logger.warning("意图分类结构化输出失败，使用规则兜底: %s", e)
            result = self._rule_classify(state)

        intent = result.intent.value
        phase = self._intent_to_phase(intent, state.phase)
        logger.debug("intent_classifier: %s -> %s (phase=%s)", state.user_input, intent, phase)
        return {"intent": intent, "phase": phase}

    def _rule_classify(self, state: ComedyState) -> IntentClassification:
        """规则兜底分类。"""
        user_input = state.user_input.strip().lower()
        phase = state.phase

        if phase in ("reviewing", "human_review", "routing_feedback"):
            if any(kw in user_input for kw in _FEEDBACK_KEYWORDS):
                return IntentClassification(
                    intent=UserIntent.FEEDBACK, confidence=0.8
                )

        if any(kw in user_input for kw in _CONTROL_KEYWORDS):
            return IntentClassification(intent=UserIntent.CONTROL, confidence=0.9)
        if any(kw in user_input for kw in _SEARCH_KEYWORDS):
            return IntentClassification(intent=UserIntent.SEARCH, confidence=0.8)
        if any(kw in state.user_input for kw in _WRITING_KEYWORDS):
            return IntentClassification(intent=UserIntent.WRITING, confidence=0.85)

        return IntentClassification(intent=UserIntent.CHAT, confidence=0.9)

    @staticmethod
    def _intent_to_phase(intent: str, current_phase: str) -> str:
        """根据意图映射到下一个 phase。"""
        if intent == "writing":
            return "analyzing"
        if intent == "search":
            return "searching"
        if intent == "control":
            return "finalizing"
        if intent == "feedback":
            return "routing_feedback"
        return "chatting"
