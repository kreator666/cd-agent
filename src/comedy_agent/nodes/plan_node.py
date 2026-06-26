"""计划节点：生成 Todo List 和段落 Outline。"""

from __future__ import annotations

import logging

from comedy_agent.core.config import settings
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PLAN_PROMPT = """你是一位脱口秀结构规划师。请根据以下分析和用户请求，生成一个创作计划。

用户请求：{user_input}
分析结果：
- 话题：{topic}
- 态度：{attitude}
- 偏见注意：{bias}
- 情绪基调：{emotion}

请输出以下 JSON 格式（不要解释，只输出 JSON）：
{{
    "todo": [
        "步骤1：...",
        "步骤2：..."
    ],
    "outline": [
        "第一段：开场/铺垫，引入话题",
        "第二段：展开观察，建立共鸣",
        "第三段：转折或升级，强化冲突",
        "第四段：收尾/Callback，给出结论"
    ],
    "tone": "整体语气建议"
}}

outline 应包含 3-5 个段落，每个段落一句话描述。
"""


def plan_node(state: ComedyState) -> dict:
    """计划生成节点。

    Args:
        state: 当前图状态。

    Returns:
        dict: 包含 plan 和 phase 更新。
    """
    model_name = state.model or settings.default_model
    llm = ModelFactory.get_model(model_name)

    analysis = state.analysis or {}
    prompt = PLAN_PROMPT.format(
        user_input=state.user_input,
        topic=analysis.get("topic", ""),
        attitude=analysis.get("attitude", ""),
        bias=analysis.get("bias", ""),
        emotion=analysis.get("emotion", ""),
    )
    response = llm.invoke([("human", prompt)])
    content = str(response.content)

    plan = _parse_plan(content)
    logger.debug("plan_node result: %s", plan)

    return {
        "plan": plan,
        "phase": "writing",
        "current_section": 0,
        "sections": [],
    }


def _parse_plan(content: str) -> dict:
    """从 LLM 输出中解析 JSON 计划。"""
    import json
    import re

    code_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if code_match:
        content = code_match.group(1).strip()

    try:
        plan = json.loads(content)
        # 确保必要字段
        plan.setdefault("todo", [])
        plan.setdefault("outline", [])
        plan.setdefault("tone", "")
        return plan
    except json.JSONDecodeError:
        logger.warning("计划结果 JSON 解析失败，使用兜底: %s", content[:200])

    # 兜底：按行解析 outline
    lines = [line.strip("- *0123456789. ") for line in content.splitlines() if line.strip()]
    outline = [line for line in lines if line]
    return {"todo": [], "outline": outline[:5], "tone": ""}
