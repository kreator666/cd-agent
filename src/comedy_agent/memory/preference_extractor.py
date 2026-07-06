"""偏好提取器。

从对话记录中提取用户创作偏好。
"""

from __future__ import annotations

import json
import re
from typing import Any


def _build_conversation_text(messages: list[dict[str, Any]]) -> str:
    """将消息列表格式化为用于偏好提取的对话文本。"""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "")
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        if role == "human":
            parts.append(f"用户: {content[:300]}")
        elif role == "ai":
            parts.append(f"AI: {content[:300]}")
        else:
            parts.append(f"{role}: {content[:300]}")
    return "\n\n".join(parts)


def _extract_json(text: str) -> dict[str, Any]:
    """从文本中提取 JSON 对象。

    支持纯 JSON、markdown 代码块、嵌在文本中的 JSON。
    """
    text = text.strip()

    # 尝试 markdown 代码块
    code_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if code_match:
        candidate = code_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 尝试整个文本
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试从文本中提取 JSON 对象
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从文本中提取 JSON: {text[:100]}")
