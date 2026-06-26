"""动态 Prompt 构建器（state_modifier）。

根据 ComedyState 与选中的 SkillConfig，动态组装四层 Prompt：
1. 基础角色层
2. Skill system_prompt 层
3. Few-shot examples 层
4. 当前段落上下文层（user prompt）
"""

from __future__ import annotations

from jinja2 import Template, UndefinedError

from comedy_agent.core.skill_loader import SkillConfig
from comedy_agent.state.schema import ComedyState


BASE_SYSTEM_PROMPT = """你是一位中文喜剧创作助手。
你的任务是根据用户请求、创作计划、已完成段落和人类反馈，生成当前段落的正文。
请保持口语化、有画面感，适合舞台表演；不要解释笑点，让笑点自然呈现。"""


DEFAULT_USER_PROMPT_TEMPLATE = """用户请求：{{ user_input }}

整体计划：
{{ outline }}

当前段落目标：
{{ section_goal }}

已完成的段落：
{{ completed_sections }}

{{ feedback_section }}

要求：
1. 只输出当前段落的正文，不要解释
2. 保持口语化、有画面感
3. 每段 2-4 句话，适合舞台表演
4. 不要解释笑点，让笑点自然呈现
"""


def _format_examples(examples: list) -> str:
    """将 SkillExample 列表格式化为 Prompt 文本。"""
    if not examples:
        return ""
    lines = ["【参考示例】"]
    for idx, ex in enumerate(examples, 1):
        lines.append(f"示例 {idx}:")
        if getattr(ex, "input", None):
            lines.append(f"输入：{ex.input}")
        lines.append(f"输出：{ex.output}")
        lines.append("")
    return "\n".join(lines).strip()


def _render(template_text: str, variables: dict) -> str:
    """使用 Jinja2 渲染模板，变量缺失时静默保留空字符串。"""
    try:
        return Template(template_text).render(**variables)
    except UndefinedError:
        # 若模板使用了未提供的变量，回退到原字符串
        return template_text


def build_prompts(state: ComedyState, skill_config: SkillConfig) -> tuple[str, str]:
    """根据 State 和 Skill 构建 (system_prompt, user_prompt)。

    Args:
        state: 当前 LangGraph 状态。
        skill_config: 选中的 Skill 配置。

    Returns:
        (system_prompt, user_prompt) 元组。
    """
    plan = state.plan or {}
    outline = plan.get("outline", [])
    section_index = state.current_section

    if section_index >= len(outline):
        section_goal = "（所有段落已完成）"
    else:
        section_goal = outline[section_index]

    completed_sections = _format_completed_sections(state.sections)
    feedback_section = _format_feedback(state.feedback)
    outline_text = "\n".join(f"{i + 1}. {goal}" for i, goal in enumerate(outline))

    variables = {
        "style": state.selected_style or "",
        "user_input": state.user_input,
        "outline": outline_text,
        "section_goal": section_goal,
        "completed_sections": completed_sections,
        "feedback_section": feedback_section,
        "section_index": section_index + 1,
        "analysis": state.analysis or {},
        "slots": state.slots or {},
    }

    # System Prompt：基础层 + Skill 层 + 示例层
    skill_system = _render(skill_config.system_prompt, variables)
    examples_text = _format_examples(skill_config.examples)

    system_parts = [BASE_SYSTEM_PROMPT, skill_system, examples_text]
    system_prompt = "\n\n".join(part for part in system_parts if part.strip())

    # User Prompt：优先使用 Skill 自带模板，否则使用默认模板
    user_template = skill_config.prompt_template or DEFAULT_USER_PROMPT_TEMPLATE
    user_prompt = _render(user_template, variables)

    return system_prompt, user_prompt


def _format_completed_sections(sections: list[str]) -> str:
    """格式化已完成的段落。"""
    if not sections:
        return "无"
    lines = []
    for i, section in enumerate(sections):
        lines.append(f"第 {i + 1} 段：{section}")
    return "\n".join(lines)


def _format_feedback(feedback: str) -> str:
    """格式化人类反馈。"""
    if not feedback:
        return ""
    return f"人类审阅反馈（请据此修改）：\n{feedback}"
