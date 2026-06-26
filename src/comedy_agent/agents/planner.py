"""创作计划 Worker。

根据用户请求和分析结果生成 Todo List 与段落 Outline。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.agents.schemas import PlanResult
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位脱口秀结构规划师。请根据以下分析和用户请求，生成一个创作计划。

用户请求：{user_input}
分析结果：
- 话题：{topic}
- 态度：{attitude}
- 偏见注意：{bias}
- 情绪基调：{emotion}

请输出：
- todo: 创作步骤清单
- outline: 3-5 个段落，每个段落一句话描述
- tone: 整体语气建议

只输出结构化结果，不要解释。"""


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
        prompt = PROMPT.format(
            user_input=state.user_input,
            topic=analysis.get("topic", ""),
            attitude=analysis.get("attitude", ""),
            bias=analysis.get("bias", ""),
            emotion=analysis.get("emotion", ""),
        )

        try:
            structured_llm = llm.with_structured_output(PlanResult)
            result: PlanResult = structured_llm.invoke([("human", prompt)])
        except Exception as e:
            logger.warning("计划结构化输出失败，使用文本兜底: %s", e)
            result = self._text_fallback(llm, prompt)

        logger.debug("planner: outline=%d", len(result.outline))
        return {
            "plan": result.model_dump(),
            "phase": "writing",
            "current_section": 0,
            "sections": [],
        }

    def _text_fallback(self, llm: BaseChatModel, prompt: str) -> PlanResult:
        """结构化输出失败时的文本兜底。"""
        import json
        import re

        response = llm.invoke([("human", prompt)])
        content = str(getattr(response, "content", response))

        code_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
        if code_match:
            content = code_match.group(1).strip()

        try:
            data = json.loads(content)
            return PlanResult(**data)
        except Exception:
            logger.warning("计划文本兜底解析失败，使用默认大纲")

        return PlanResult(
            todo=["分析", "写作", "审核"],
            outline=[
                "第一段：开场/铺垫，引入话题",
                "第二段：展开观察，建立共鸣",
                "第三段：转折或升级，强化冲突",
                "第四段：收尾/Callback，给出结论",
            ],
            tone="日常观察",
        )
