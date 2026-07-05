"""长对话摘要服务。

当对话历史超过阈值时，对早期消息调用 LLM 生成摘要，保留核心需求与关键约束，
避免创作类 Agent 因截断而丢失上下文。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from comedy_agent.core.config import settings
from comedy_agent.models.factory import ModelFactory

logger = logging.getLogger(__name__)

_DEFAULT_SUMMARY_PROMPT = (
    "请对下面的对话历史进行精炼摘要。要求：\n"
    "1. 保留用户的核心需求、创作主题、风格偏好、关键约束和已确认的信息；\n"
    "2. 忽略重复、寒暄、无关紧要的内容；\n"
    "3. 用第三人称、简洁中文输出，不超过 300 字；\n"
    "4. 只输出摘要内容，不要添加标题或解释。\n\n"
    "对话历史：\n{history}\n\n摘要："
)


async def summarize_messages(
    messages: list[BaseMessage],
    model: str | None = None,
    max_summary_tokens: int = 300,
    max_input_messages: int = 20,
) -> str:
    """对过长历史消息生成摘要。

    Args:
        messages: 完整历史消息列表。
        model: 指定模型名称，为 None 时使用 settings.default_model。
        max_summary_tokens: 摘要最大 token 数（供模型 max_tokens 参数使用）。
        max_input_messages: 用于生成摘要的早期消息条数，超过部分会被截断。

    Returns:
        str: 对话摘要文本；生成失败时返回空字符串。
    """
    if not messages:
        return ""

    # 取早期消息生成摘要，避免输入过长
    history_messages = messages[:max_input_messages]
    history_text = _format_history_for_summary(history_messages)

    prompt = _DEFAULT_SUMMARY_PROMPT.format(history=history_text)

    try:
        model_name = model or settings.default_model
        llm = ModelFactory.get_model(model_name)
        response = await llm.ainvoke([SystemMessage(content=prompt)])
        summary = str(response.content or "").strip()
        logger.debug(
            "生成对话摘要成功，模型=%s，输入消息数=%d，摘要长度=%d",
            model_name,
            len(history_messages),
            len(summary),
        )
        return summary
    except Exception:
        logger.exception("生成对话摘要失败")
        return ""


def _format_history_for_summary(messages: list[BaseMessage]) -> str:
    """把消息列表格式化为适合摘要的纯文本。"""
    lines: list[str] = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", "")
        if role == "human":
            lines.append(f"用户：{content}")
        elif role == "ai":
            lines.append(f"助手：{content}")
        elif role == "system":
            lines.append(f"系统：{content}")
        elif role == "tool":
            lines.append(f"工具：{content}")
        else:
            lines.append(f"{role}：{content}")
    return "\n".join(lines)
