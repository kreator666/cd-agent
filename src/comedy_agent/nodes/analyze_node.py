"""分析节点：对用户输入进行四维度分析。

话题 / 态度 / 偏见 / 情绪
"""

from __future__ import annotations

import logging

from comedy_agent.core.config import settings
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """你是一位喜剧创作分析助手。请对用户的创作请求进行四维度分析，只输出 JSON，不要解释。

用户请求：{user_input}

请输出以下 JSON 格式：
{{
    "topic": "核心话题（10字以内）",
    "attitude": "创作者对话题的态度，如讽刺/自嘲/观察/批判/温情",
    "bias": "可能存在的认知偏见或刻板印象，如没有则写'无'",
    "emotion": "目标情绪基调，如愤怒/荒诞/尴尬/温暖/无奈"
}}
"""


def analyze_node(state: ComedyState) -> dict:
    """四维度分析节点。

    Args:
        state: 当前图状态。

    Returns:
        dict: 包含 analysis 和 phase 更新。
    """
    model_name = state.model or settings.default_model
    llm = ModelFactory.get_model(model_name)

    prompt = ANALYSIS_PROMPT.format(user_input=state.user_input)
    response = llm.invoke([("human", prompt)])
    content = str(response.content)

    analysis = _parse_analysis(content)
    logger.debug("analyze_node result: %s", analysis)

    return {
        "analysis": analysis,
        "phase": "planning",
    }


def _parse_analysis(content: str) -> dict:
    """从 LLM 输出中解析 JSON 分析结果。"""
    import json
    import re

    # 尝试从 Markdown 代码块中提取
    code_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if code_match:
        content = code_match.group(1).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("分析结果 JSON 解析失败，使用兜底: %s", content[:200])

    # 兜底：从文本中提取关键信息
    return {
        "topic": _extract_field(content, "topic", "话题"),
        "attitude": _extract_field(content, "attitude", "态度"),
        "bias": _extract_field(content, "bias", "偏见"),
        "emotion": _extract_field(content, "emotion", "情绪"),
    }


def _extract_field(content: str, en_name: str, cn_name: str) -> str:
    """简单字段提取兜底。"""
    import re

    patterns = [
        rf'"{en_name}"\s*[:：]\s*"([^"]+)"',
        rf'"{cn_name}"\s*[:：]\s*"([^"]+)"',
        rf"{cn_name}\s*[:：]\s*([^\n,，。]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()
    return "未识别"
