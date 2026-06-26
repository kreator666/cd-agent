"""写作 Worker。

根据大纲逐段撰写脱口秀内容。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位脱口秀写手。请根据以下计划和反馈，撰写第 {section_index} 段内容。

用户请求：{user_input}
整体计划：
{outline}

当前段落目标：{section_goal}

已完成的段落：
{completed_sections}

{feedback_section}

要求：
1. 只输出当前段落的正文，不要解释
2. 保持口语化、有画面感
3. 每段 2-4 句话，适合舞台表演
4. 不要解释笑点，让笑点自然呈现
"""


class WriterAgent:
    """写手 Agent。"""

    def run(self, state: ComedyState, llm: BaseChatModel | None = None) -> dict[str, Any]:
        """撰写当前段落。

        Args:
            state: 当前图状态。
            llm: 可选的外部 LLM。

        Returns:
            包含 ``sections`` 与 ``phase`` 的更新字典。
        """
        if llm is None:
            llm = ModelFactory.get_model(
                state.model, task_type="creative"
            )

        plan = state.plan or {}
        outline = plan.get("outline", [])
        section_index = state.current_section

        if section_index >= len(outline):
            logger.debug("writer: all sections done, move to finalizing")
            return {"phase": "finalizing"}

        section_goal = outline[section_index]
        completed_sections = self._format_completed_sections(state.sections)
        feedback_section = self._format_feedback(state.feedback)

        prompt = PROMPT.format(
            section_index=section_index + 1,
            user_input=state.user_input,
            outline="\n".join(f"{i+1}. {goal}" for i, goal in enumerate(outline)),
            section_goal=section_goal,
            completed_sections=completed_sections,
            feedback_section=feedback_section,
        )

        response = llm.invoke([("human", prompt)])
        section_text = str(getattr(response, "content", response)).strip()

        sections = state.sections.copy()
        if section_index < len(sections):
            sections[section_index] = section_text
        else:
            sections.append(section_text)

        logger.debug("writer: section %d completed", section_index)
        return {
            "sections": sections,
            "phase": "reviewing",
        }

    @staticmethod
    def _format_completed_sections(sections: list[str]) -> str:
        """格式化已完成的段落。"""
        if not sections:
            return "无"
        lines = []
        for i, section in enumerate(sections):
            lines.append(f"第 {i+1} 段：{section}")
        return "\n".join(lines)

    @staticmethod
    def _format_feedback(feedback: str) -> str:
        """格式化人类反馈。"""
        if not feedback:
            return ""
        return f"人类审阅反馈（请据此修改）：\n{feedback}"
