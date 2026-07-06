"""创作计划 Worker。

根据用户请求和分析结果生成 Todo List 与段落 Outline。
使用普通文本输出 + 稳健解析，兼容返回 markdown/非 JSON 的模型。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AnyMessage

from comedy_agent.agents.schemas import PlanResult
from comedy_agent.core.knowledge_system import retrieve_knowledge
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位脱口秀结构规划师。请根据完整对话历史、分析结果和相关喜剧理论知识，生成一个创作计划。

## 历史摘要（如没有则忽略）
{conversation_summary}

## 最近对话历史
{conversation_history}

## 上一轮计划（如没有则忽略）
{previous_plan}

## 当前分析结果
- 话题：{topic}
- 态度：{attitude}
- 偏见注意：{bias}
- 情绪基调：{emotion}

## 各维度最终理解（基于用户专项对话总结）
{slot_summaries}

## 可参考的喜剧理论/技法/结构模板
{knowledge_context}

请在大纲中适当引用上述技法或结构模板名称，让计划更具喜剧专业度。

请严格按以下格式输出：

todo:
1. 第一步任务
2. 第二步任务
3. 第三步任务

outline:
1. 第一段一句话描述
2. 第二段一句话描述
3. 第三段一句话描述
4. 第四段一句话描述（可选）
5. 第五段一句话描述（可选）

tone: 整体语气建议，如“讽刺、自嘲、温暖”

只输出上述格式，不要解释、不要 markdown 代码块。"""


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


def _format_previous_plan(plan: dict[str, Any] | None) -> str:
    """把上一轮计划格式化为文本。"""
    if not plan:
        return "（无）"
    lines = []
    todo = plan.get("todo") or []
    outline = plan.get("outline") or []
    tone = plan.get("tone", "")
    if todo:
        lines.append("todo:")
        lines.extend(f"{i}. {t}" for i, t in enumerate(todo, 1))
    if outline:
        lines.append("outline:")
        lines.extend(f"{i}. {o}" for i, o in enumerate(outline, 1))
    if tone:
        lines.append(f"tone: {tone}")
    return "\n".join(lines) if lines else "（无）"

_DEFAULT_RESULT = PlanResult(
    todo=["分析话题", "生成大纲", "逐段写作", "整体审核"],
    outline=[
        "第一段：开场/铺垫，引入话题",
        "第二段：展开观察，建立共鸣",
        "第三段：转折或升级，强化冲突",
        "第四段：收尾/Callback，给出结论",
    ],
    tone="日常观察",
)


class PlannerAgent:
    """创作计划 Agent。"""

    def run(self, state: ComedyState, llm: BaseChatModel | None = None) -> dict[str, Any]:
        """生成创作计划。

        Args:
            state: 当前图状态。
            llm: 可选的外部 LLM。

        Returns:
            包含 ``plan``、``phase``、``current_section``、``sections`` 的更新字典。
        """
        if llm is None:
            llm = ModelFactory.get_model(
                state.model, task_type="analytical"
            )

        analysis = state.analysis or {}
        slot_summaries = self._summarize_slot_conversations(state, llm)
        knowledge_context, knowledge_references = self._retrieve_knowledge(analysis, state.user_input)
        prompt = PROMPT.format(
            conversation_summary=state.conversation_summary or "（无）",
            conversation_history=_format_history(state.messages),
            previous_plan=_format_previous_plan(state.plan),
            topic=analysis.get("topic", ""),
            attitude=analysis.get("attitude", ""),
            bias=analysis.get("bias", ""),
            emotion=analysis.get("emotion", ""),
            slot_summaries=slot_summaries,
            knowledge_context=knowledge_context,
        )

        try:
            response = llm.invoke([("human", prompt)])
            content = str(getattr(response, "content", response))
            result = self._parse_content(content)
        except Exception as e:
            logger.warning("计划生成调用失败，使用默认大纲: %s", e)
            result = _DEFAULT_RESULT

        logger.debug("planner: outline=%d", len(result.outline))
        plan_dict = result.model_dump()
        if knowledge_references:
            plan_dict["knowledge_references"] = knowledge_references
        return {
            "plan": plan_dict,
            "phase": "plan_review",
            "current_section": 0,
            "sections": [],
        }

    @staticmethod
    def _summarize_slot_conversations(
        state: ComedyState, llm: BaseChatModel
    ) -> str:
        """四个维度都填满时，对各维度独立对话历史做总结。

        若维度未填满或无专项对话历史，返回空字符串。
        """
        slots = state.slots or {}
        slot_conversations = state.slot_conversations or {}

        # 判断四个维度是否都已收集（中文 slots 优先）
        required = ("话题", "态度", "偏见", "情绪")
        if not all(slots.get(dim) for dim in required):
            return "（维度未集齐，不做专项总结）"

        if not slot_conversations:
            return "（无专项对话历史）"

        summary_lines: list[str] = []
        for dim in required:
            msgs = slot_conversations.get(dim)
            if not msgs:
                summary_lines.append(f"- {dim}：{slots.get(dim, '')}")
                continue

            history_text = _format_history(msgs, max_turns=6)
            prompt = (
                f"请根据用户与助手关于「{dim}」的以下对话，"
                f"总结用户最终想要的 {dim}。只输出一句话。\n\n{history_text}"
            )
            try:
                response = llm.invoke([("human", prompt)])
                summary = str(getattr(response, "content", response)).strip()
            except Exception as e:
                logger.warning("总结 %s 维度对话失败: %s", dim, e)
                summary = slots.get(dim, "")
            summary_lines.append(f"- {dim}：{summary}")

        return "\n".join(summary_lines)

    @staticmethod
    def _retrieve_knowledge(
        analysis: dict[str, Any],
        user_input: str,
        top_k: int = 5,
    ) -> tuple[str, list[dict[str, Any]]]:
        """根据话题检索相关理论知识。

        Returns:
            (knowledge_context, knowledge_references)
        """
        query = analysis.get("topic") or user_input
        if not query:
            return "（无）", []

        try:
            items = retrieve_knowledge(query, top_k=top_k)
        except Exception as e:
            logger.warning("Planner 知识检索失败: %s", e)
            return "（无）", []

        if not items:
            return "（无）", []

        lines: list[str] = []
        references: list[dict[str, Any]] = []
        for idx, item in enumerate(items, 1):
            lines.append(
                f"{idx}. {item.title}（{item.category}）：{item.summary or item.content}"
            )
            references.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "category": item.category,
                    "source": item.source,
                }
            )
        return "\n".join(lines), references

    def _parse_content(self, content: str) -> PlanResult:
        """从普通文本中解析 todo / outline / tone。"""
        # 尝试先去掉可能的 markdown 代码块标记
        text = re.sub(r"```(?:json|markdown|text)?\s*", "", content)
        text = text.replace("```", "")

        sections: dict[str, str] = {}
        current_key: str | None = None
        current_lines: list[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            header_match = re.match(r"^(todo|outline|tone)[:：]\s*(.*)$", stripped, re.IGNORECASE)
            if header_match:
                if current_key is not None:
                    sections[current_key] = "\n".join(current_lines)
                current_key = header_match.group(1).lower()
                rest = header_match.group(2).strip()
                current_lines = [rest] if rest else []
            elif current_key is not None and stripped:
                current_lines.append(stripped)

        if current_key is not None:
            sections[current_key] = "\n".join(current_lines)

        todo = self._extract_list_items(sections.get("todo", ""))
        outline = self._extract_list_items(sections.get("outline", ""))
        tone = sections.get("tone", "").strip() or _DEFAULT_RESULT.tone

        if not todo or not outline:
            logger.warning("计划解析结果不完整，使用默认大纲")
            return _DEFAULT_RESULT

        return PlanResult(todo=todo, outline=outline, tone=tone)

    @staticmethod
    def _extract_list_items(text: str) -> list[str]:
        """从编号/ bullet 列表中提取条目。"""
        items: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(?:\d+[.．、]|[-\*•])\s*(.+)$", line)
            if match:
                items.append(match.group(1).strip())
        return items
