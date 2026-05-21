"""用户偏好自动提取器。

每次对话结束后，用轻量模型分析对话内容，提取用户的创作偏好，
以结构化 KV 形式保存到 user_preferences 表。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.models.factory import ModelFactory

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = """\
你是一位用户偏好分析师。请根据下面的对话记录，提取用户的创作偏好。

对话记录：
{conversation_text}

请分析并输出以下格式的 JSON（只输出 JSON，不要其他内容）：
{{
  "preferred_style": "用户喜欢的喜剧风格，如吐槽风、荒诞风、温情风等，没有则省略",
  "disliked_tropes": ["用户明确讨厌的梗或套路，没有则省略"],
  "preferred_duration": "用户偏好的作品时长，如3分钟、5-10分钟，没有则省略",
  "preferred_audience": "用户偏好的受众，如年轻人、职场人，没有则省略",
  "preferred_script_type": "用户偏好的作品类型，如standup/sketch/crosstalk/sitcom，没有则省略",
  "creative_notes": "其他创作相关的偏好或习惯，没有则省略"
}}

注意：
1. 只提取用户明确表达或强烈暗示的偏好
2. 如果某一项无法确定，直接省略该字段，不要编造
3. 不要输出任何解释，只输出 JSON
"""


def _build_conversation_text(messages: list[dict[str, Any]]) -> str:
    """将消息列表格式化为对话文本。"""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        role_name = {"human": "用户", "ai": "AI", "system": "系统", "tool": "工具"}.get(role, role)
        lines.append(f"{role_name}: {content[:300]}")
    return "\n\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 输出中提取 JSON 对象。"""
    # 尝试直接解析
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取最外层的大括号
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError("无法从 LLM 输出中解析 JSON")


def extract_preferences(
    messages: list[dict[str, Any]],
    prompt: str | None = None,
) -> dict[str, Any]:
    """从对话记录中提取用户偏好。

    Args:
        messages: 对话消息列表，格式为 [{"role": "human", "content": "..."}, ...]。
        prompt: 自定义提取 Prompt，为 None 时使用默认模板。

    Returns:
        提取到的偏好字典，键值对应标准 schema。提取失败返回空字典。
    """
    conversation_text = _build_conversation_text(messages)
    if not conversation_text:
        return {}

    try:
        llm = ModelFactory.get_model_with_fallback(task_type="fast")
    except Exception as e:
        logger.warning("偏好提取：无法加载 fast_model: %s", e)
        return {}

    system_prompt = (prompt or DEFAULT_PROMPT).format(conversation_text=conversation_text)

    try:
        response = llm.invoke(system_prompt)
        raw_text = str(response.content if hasattr(response, "content") else response)
        prefs = _extract_json(raw_text)

        # 过滤空值和无效值
        result = {}
        for key, value in prefs.items():
            if value is None:
                continue
            if isinstance(value, list) and not value:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            result[key] = value

        if result:
            logger.info("偏好提取结果: %s", result)
        return result

    except Exception as e:
        logger.warning("偏好提取失败: %s", e)
        return {}


def merge_preferences(user_id: str, new_prefs: dict[str, Any], memory: UnifiedMemory | None = None) -> None:
    """将新提取的偏好合并到用户偏好表中（新值覆盖旧值）。

    Args:
        user_id: 用户唯一标识。
        new_prefs: 新提取的偏好字典。
        memory: UnifiedMemory 实例，为 None 时自动创建。
    """
    if not new_prefs:
        return

    if memory is None:
        try:
            memory = UnifiedMemory()
        except Exception as e:
            logger.warning("偏好合并：无法初始化 UnifiedMemory: %s", e)
            return

    for key, value in new_prefs.items():
        try:
            memory.save_preference(user_id, key, value)
            logger.debug("偏好已更新: %s = %s", key, value)
        except Exception as e:
            logger.warning("偏好保存失败 (%s): %s", key, e)
