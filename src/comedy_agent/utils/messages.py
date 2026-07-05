"""消息转换工具。

提供数据库存储格式（{"role": "human/ai/system/tool", "content": "..."}）
与 LangChain BaseMessage 对象之间的双向转换。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


def _normalize_role(role: str) -> str:
    """统一 role 字符串，兼容常见别名。"""
    role = (role or "human").lower().strip()
    aliases = {
        "user": "human",
        "assistant": "ai",
        "bot": "ai",
        "function": "tool",
    }
    return aliases.get(role, role)


def dicts_to_messages(dicts: list[dict[str, Any]]) -> list[BaseMessage]:
    """将数据库中存储的 dict 列表转换为 LangChain Message 对象列表。

    Args:
        dicts: 每条消息为 {"role": "human/ai/system/tool", "content": "..."}。

    Returns:
        list[BaseMessage]: LangChain 消息对象列表。
    """
    messages: list[BaseMessage] = []
    for item in dicts:
        if not isinstance(item, dict):
            continue
        role = _normalize_role(item.get("role", "human"))
        content = item.get("content", "")
        if role == "human":
            messages.append(HumanMessage(content=content))
        elif role == "ai":
            messages.append(AIMessage(content=content))
        elif role == "system":
            messages.append(SystemMessage(content=content))
        elif role == "tool":
            # 数据库格式未保存 tool_call_id，使用空字符串占位
            messages.append(
                ToolMessage(content=str(content), tool_call_id=item.get("tool_call_id", ""))
            )
        else:
            # 未知 role 安全降级为 human
            messages.append(HumanMessage(content=str(content)))
    return messages


def messages_to_dicts(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """将 LangChain Message 对象列表转换为数据库存储的 dict 列表。

    Args:
        messages: LangChain 消息对象列表。

    Returns:
        list[dict[str, Any]]: 每条消息为 {"role": "human/ai/system/tool", "content": "..."}。
    """
    dicts: list[dict[str, Any]] = []
    for msg in messages:
        role = getattr(msg, "type", "human")
        content = getattr(msg, "content", "")
        item: dict[str, Any] = {"role": role, "content": content}
        if isinstance(msg, ToolMessage):
            item["tool_call_id"] = getattr(msg, "tool_call_id", "")
        dicts.append(item)
    return dicts
