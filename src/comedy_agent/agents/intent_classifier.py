"""意图分类 Worker。

使用普通文本输出 + 正则解析，兼容不支持结构化输出的模型。
支持 7 类意图：writing / fill_slot / control / search / feedback / consult / chat。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.agents.schemas import UserIntent
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位意图分类助手。请根据用户输入判断其意图，并严格按以下格式输出：

意图: <writing | fill_slot | search | control | feedback | consult | chat>
置信度: 0-1 之间的数字
理由: 一句话说明原因

判断标准：
- writing：用户明确要创作某个具体主题的内容（如“写一段关于...的脱口秀”），且没有使用 @ 填槽。
- fill_slot：用户通过 @ 或显式声明在填写 4 维度槽位（话题 / 态度 / 偏见 / 情绪）。
- search：用户想搜索资料、找素材、查信息。
- control：停止、结束、退出、重置、清空当前任务。
- feedback：用户在审阅阶段给出通过、修改、重写、继续等反馈。
- consult：用户在咨询、提问、不确定怎么填槽、或就着当前状态深入聊天以确认需求；不是明确的命令。
- chat：普通闲聊或问候，与当前创作流程无关。

当前会话阶段: {phase}
已收集槽位: {slots}
用户输入: {user_input}

只输出“意图/置信度/理由”三行，不要任何解释或 markdown。"""

# 规则兜底关键词
_WRITING_KEYWORDS = (
    "写", "创作", "来一段", "写一段", "写个", "来个", "段子", "脱口秀",
    "小品", "相声", "漫才", "剧本",
)
_SEARCH_KEYWORDS = ("搜索", "查一下", "查", "找", "资料", "素材")
_CONTROL_KEYWORDS = ("停止", "结束", "退出", "重置", "清空")
_FEEDBACK_KEYWORDS = ("通过", "修改", "重写", "继续", "ok", "yes", "no")
_SLOT_KEYWORDS = ("话题", "态度", "偏见", "情绪")
_CONSULT_KEYWORDS = (
    "怎么", "如何", "什么", "哪些", "吗？", "呢？", "吗?", "呢?",
    "不知道", "不太懂", "不清楚", "咨询", "建议", "选项", "帮我看看",
)


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
                state.model, task_type="fast"
            )

        prompt = PROMPT.format(
            phase=state.phase,
            slots=_format_slots(state.slots),
            user_input=state.user_input,
        )
        try:
            response = llm.invoke([("human", prompt)])
            content = str(getattr(response, "content", response))
            result, has_header = self._parse_content(content)
            # 若 LLM 没有按格式输出且被归为 chat，用规则兜底修正，避免 token 浪费
            if not has_header and result.intent == UserIntent.CHAT:
                rule_result = self._rule_classify(state)
                if rule_result.intent != UserIntent.CHAT:
                    result = rule_result
        except Exception as e:
            logger.warning("意图分类调用失败，使用规则兜底: %s", e)
            result = self._rule_classify(state)

        intent = result.intent.value
        phase = self._intent_to_phase(intent, state.phase)
        logger.debug(
            "intent_classifier: input=%s -> intent=%s phase=%s",
            state.user_input,
            intent,
            phase,
        )
        return {"intent": intent, "phase": phase}

    def _parse_content(self, content: str) -> tuple[IntentClassificationResult, bool]:
        """从 LLM 文本输出中解析意图。

        Returns:
            (分类结果, 是否包含标准“意图：”头)
        """
        lowered = content.lower()

        # 直接匹配“意图: xxx”
        match = re.search(r"意图[:：]\s*(\w+)", content)
        if match:
            raw = match.group(1).strip().lower()
            intent = self._normalize_intent(raw)
            if intent:
                return IntentClassificationResult(intent=intent), True

        # 兜底：根据文本中出现的关键词判断（无标准头时）
        if any(kw in lowered for kw in ("feedback", "通过", "修改", "重写", "继续")):
            return IntentClassificationResult(UserIntent.FEEDBACK), False
        if any(kw in lowered for kw in ("fill_slot", "填槽", "槽位")):
            return IntentClassificationResult(UserIntent.FILL_SLOT), False
        if any(kw in lowered for kw in ("control", "停止", "结束", "退出", "重置")):
            return IntentClassificationResult(UserIntent.CONTROL), False
        if any(kw in lowered for kw in ("search", "搜索", "查", "找资料")):
            return IntentClassificationResult(UserIntent.SEARCH), False
        if any(kw in lowered for kw in ("writing", "创作", "写作", "写一段")):
            return IntentClassificationResult(UserIntent.WRITING), False
        if any(kw in lowered for kw in ("consult", "咨询", "建议", "怎么")):
            return IntentClassificationResult(UserIntent.CONSULT), False

        return IntentClassificationResult(UserIntent.CHAT), False

    def _rule_classify(self, state: ComedyState) -> IntentClassificationResult:
        """规则兜底分类。"""
        user_input = state.user_input.strip()
        lowered = user_input.lower()
        phase = state.phase

        if phase in ("reviewing", "human_review", "routing_feedback"):
            if any(kw in lowered for kw in _FEEDBACK_KEYWORDS):
                return IntentClassificationResult(UserIntent.FEEDBACK)

        if any(kw in lowered for kw in _CONTROL_KEYWORDS):
            return IntentClassificationResult(UserIntent.CONTROL)

        if any(kw in lowered for kw in _SEARCH_KEYWORDS):
            return IntentClassificationResult(UserIntent.SEARCH)

        # 明确的 @ 填槽
        if "@" in user_input or any(f"{kw}" in user_input for kw in _SLOT_KEYWORDS):
            # 如果包含创作关键词且没有 @，可能是显式声明槽位
            return IntentClassificationResult(UserIntent.FILL_SLOT)

        # 咨询类（非明确命令）
        if any(kw in user_input for kw in _CONSULT_KEYWORDS):
            return IntentClassificationResult(UserIntent.CONSULT)

        if any(kw in user_input for kw in _WRITING_KEYWORDS):
            return IntentClassificationResult(UserIntent.WRITING)

        return IntentClassificationResult(UserIntent.CHAT)

    @staticmethod
    def _normalize_intent(raw: str) -> UserIntent | None:
        """将原始意图字符串归一化为枚举。"""
        mapping = {
            "writing": UserIntent.WRITING,
            "write": UserIntent.WRITING,
            "fill_slot": UserIntent.FILL_SLOT,
            "fillslot": UserIntent.FILL_SLOT,
            "control": UserIntent.CONTROL,
            "search": UserIntent.SEARCH,
            "feedback": UserIntent.FEEDBACK,
            "consult": UserIntent.CONSULT,
            "chat": UserIntent.CHAT,
        }
        return mapping.get(raw)

    @staticmethod
    def _intent_to_phase(intent: str, current_phase: str) -> str:
        """根据意图映射到下一个 phase。"""
        if intent == "writing":
            return "filling_slots"
        if intent == "fill_slot":
            return "filling_slots"
        if intent == "search":
            return "searching"
        if intent == "control":
            return "finalizing"
        if intent == "feedback":
            return "routing_feedback"
        if intent == "consult":
            return "consulting"
        return "chatting"


class IntentClassificationResult:
    """内部解析结果，兼容原来的 Pydantic 结构。"""

    def __init__(self, intent: UserIntent, confidence: float = 0.9) -> None:
        self.intent = intent
        self.confidence = confidence


def _format_slots(slots: dict[str, str] | None) -> str:
    """将槽位格式化为提示文本。"""
    if not slots:
        return "无"
    return ", ".join(f"{k}={v}" for k, v in slots.items())
