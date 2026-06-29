"""引导/建议 Worker。

当用户处于咨询、闲聊或不确定下一步时，GuideAgent 根据当前状态
给出自然语言回复 + A/B/C 三个可选项。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位专业的喜剧创作助手。请根据当前会话状态，回应用户的问题或给出下一步建议。

请严格按以下格式输出：

回复: <一段自然、口语化、有亲和力的引导语，可包含 emoji>
选项:
A. <第一个可点击选项的具体文案>
B. <第二个可点击选项的具体文案>
C. <第三个可点击选项的具体文案>

当前会话阶段: {phase}
系统支持的能力: {skills}
已收集槽位: {slots}
当前计划: {plan}
已生成段落: {sections}
用户输入: {user_input}

选项要求：
- 必须给出 A/B/C 三个选项
- 选项文案要具体可操作，用户点击后可直接发送
- 如果用户在问“你能做什么 / 能写什么 / 有哪些能力”，回复里必须列举系统支持的能力（如脱口秀、单口喜剧、段子等），并给出相关选项
- 如果槽位缺失，优先建议补充缺失维度（如“@话题 加班”）
- 如果槽位已全，建议进入下一步（生成计划 / 开始写作 / 通过当前段）
- 如果用户在咨询，先回答疑问，再给出可能的下一步

只输出“回复”和“选项”，不要解释。"""


class GuideAgent:
    """引导建议 Agent。"""

    def run(self, state: ComedyState, llm: BaseChatModel | None = None) -> dict[str, Any]:
        """生成引导回复与 A/B/C 选项。

        Args:
            state: 当前图状态。
            llm: 可选的外部 LLM。

        Returns:
            包含 ``output``、``response_type=guide``、``suggested_actions`` 的字典。
        """
        if llm is None:
            llm = ModelFactory.get_model(
                state.model, task_type="fast"
            )

        prompt = PROMPT.format(
            phase=state.phase,
            skills=_format_skills(getattr(state, "available_skills", None)),
            slots=_format_slots(state.slots),
            plan=_format_plan(state.plan),
            sections=_format_sections(state.sections),
            user_input=state.user_input,
        )

        try:
            response = llm.invoke([("human", prompt)])
            content = str(getattr(response, "content", response))
            reply, actions = self._parse_content(content)
        except Exception as e:
            logger.warning("GuideAgent 调用失败，使用兜底建议: %s", e)
            reply, actions = self._fallback_suggestions(state)

        return {
            "output": reply,
            "response_type": "guide",
            "phase": "complete",
            "suggested_actions": actions,
        }

    def _parse_content(self, content: str) -> tuple[str, list[dict[str, str]]]:
        """解析 LLM 输出为回复与选项列表。"""
        # 提取回复
        reply_match = re.search(r"回复[:：]\s*(.*?)(?=\n选项[:：]|$)", content, re.DOTALL)
        reply = reply_match.group(1).strip() if reply_match else content.strip()

        # 提取 A/B/C 选项
        actions: list[dict[str, str]] = []
        option_section_match = re.search(r"选项[:：]\s*(.*?)(?:\n\n|$)", content, re.DOTALL)
        option_section = option_section_match.group(1) if option_section_match else ""

        for line in option_section.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^([A-C])[.．、\s]+(.+)$", line)
            if match:
                label, value = match.groups()
                actions.append({
                    "label": f"{label}. {value.strip()}",
                    "action": "select_option",
                    "value": value.strip(),
                })

        if len(actions) < 3:
            # 兜底：补默认选项
            defaults = [
                {"label": "A. 继续当前流程", "action": "select_option", "value": "继续"},
                {"label": "B. 返回重新说明需求", "action": "select_option", "value": "我想重新说明需求"},
                {"label": "C. 问问怎么填槽", "action": "select_option", "value": "我不知道怎么填槽"},
            ]
            actions = actions + defaults[len(actions):]

        return reply, actions[:3]

    def _fallback_suggestions(self, state: ComedyState) -> tuple[str, list[dict[str, str]]]:
        """兜底建议。"""
        slots = state.slots or {}
        missing = [s for s in ("话题", "态度", "偏见", "情绪") if not slots.get(s)]
        user_input = (state.user_input or "").lower()
        capability_keywords = ("能做什么", "会什么", "能写什么", "有哪些能力", "能写")
        is_capability_question = any(kw in user_input for kw in capability_keywords)

        if is_capability_question:
            skills = getattr(state, "available_skills", None) or ["脱口秀", "单口喜剧", "段子"]
            reply = (
                "我可以帮你创作多种喜剧内容，比如：" + "、".join(skills) + "。"
                "你可以直接说想写什么，或者先和我一起确定话题、态度等 4 个维度。"
            )
            actions = [
                {"label": "A. 写一段脱口秀", "action": "select_option", "value": "写一段脱口秀"},
                {"label": "B. 先确定 4 个维度", "action": "select_option", "value": "怎么确定 4 个维度"},
                {"label": "C. 我想重新说明需求", "action": "select_option", "value": "我想重新说明需求"},
            ]
        elif missing:
            reply = (
                "没关系，我们一步步来。创作前需要先明确 4 个维度："
                "话题、态度、偏见、情绪。你可以直接 @ 我说明，比如："
            )
            actions = [
                {"label": f"A. @话题 加班", "action": "select_option", "value": "@话题 加班"},
                {"label": f"B. @态度 讽刺", "action": "select_option", "value": "@态度 讽刺"},
                {"label": f"C. 什么是偏见和情绪？", "action": "select_option", "value": "什么是偏见和情绪？"},
            ]
        else:
            reply = "4 个维度已经收集齐了，接下来我可以帮你生成创作计划。"
            actions = [
                {"label": "A. 生成计划", "action": "select_option", "value": "生成计划"},
                {"label": "B. 修改槽位", "action": "select_option", "value": "我想修改槽位"},
                {"label": "C. 直接开始写作", "action": "select_option", "value": "直接开始写作"},
            ]

        return reply, actions


def _format_slots(slots: dict[str, str] | None) -> str:
    if not slots:
        return "无"
    return ", ".join(f"{k}={v}" for k, v in slots.items())


def _format_plan(plan: dict[str, Any] | None) -> str:
    if not plan:
        return "无"
    outline = plan.get("outline", [])
    return "; ".join(outline) if outline else "无"


def _format_sections(sections: list[str] | None) -> str:
    if not sections:
        return "无"
    return f"{len(sections)} 段"


def _format_skills(skills: list[str] | None) -> str:
    if not skills:
        return "写脱口秀、单口喜剧、段子等喜剧文本"
    return "、".join(skills)
