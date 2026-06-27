"""写作 Worker。

根据大纲逐段撰写脱口秀内容，支持运行时加载 Skill。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.core.config import settings
from comedy_agent.core.example_retriever import retrieve_examples
from comedy_agent.core.skill_loader import (
    SkillConfig,
    get_default_skill_config,
    load_skill_config,
)
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


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
        plan = state.plan or {}
        outline = plan.get("outline", [])
        section_index = state.current_section

        if section_index >= len(outline):
            logger.debug("writer: all sections done, move to finalizing")
            return {"phase": "finalizing"}

        skill_config = self._resolve_skill_config(state)

        if llm is None:
            llm = ModelFactory.get_model(
                state.model, task_type=skill_config.task_type
            )

        # 动态检索相关示例（失败时回退到 Skill 静态示例）
        retrieved_examples: list = []
        section_goal = (state.plan or {}).get("outline", [])[state.current_section] if state.current_section < len((state.plan or {}).get("outline", [])) else ""
        if section_goal:
            try:
                retrieved_examples = retrieve_examples(
                    query=section_goal,
                    kind=skill_config.metadata.get("kind"),
                    style=state.selected_style,
                    user_id=state.user_id,
                    top_k=5,
                )
            except Exception as e:
                logger.warning("动态示例检索失败，使用 Skill 静态示例: %s", e)

        # 延迟导入避免与 graph 包产生循环引用
        from comedy_agent.graph.state_modifier import build_prompts

        system_prompt, user_prompt = build_prompts(
            state, skill_config, retrieved_examples=retrieved_examples
        )

        response = llm.invoke(
            [("system", system_prompt), ("human", user_prompt)]
        )
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
            "skill_meta": {
                "skill_id": skill_config.id,
                "skill_name": skill_config.name,
                "style": state.selected_style,
            },
        }

    @staticmethod
    def _resolve_skill_config(state: ComedyState) -> SkillConfig:
        """根据 State 解析要使用的 SkillConfig。"""
        skill_id = state.selected_skill
        if skill_id:
            cfg = load_skill_config(settings.skills_dir / skill_id)
            if cfg is not None:
                return cfg
            logger.warning("指定的 Skill %s 不存在，回退到默认 Skill", skill_id)

        default = get_default_skill_config(settings.skills_dir)
        # 如果没有 my_skill，默认 Skill 的 id 是 default
        return default
