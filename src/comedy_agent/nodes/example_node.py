"""样例引导写作节点。

在大纲确认后，先由 LLM 为当前段落生成 3 个参考样例，
然后通过 interrupt() 暂停，等待用户输入自己的段落文本。
用户输入将直接作为当前段落的产物进入审阅链路。
"""

from __future__ import annotations

import json
import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.types import interrupt

from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


_EXAMPLES_GENERATION_PROMPT = """你是一名中文脱口秀编剧。当前创作任务如下：

## 段落目标
{section_goal}

## 四维度分析
- 话题：{topic}
- 态度：{attitude}
- 偏见/视角：{bias}
- 情绪：{emotion}

## 风格
{style}

## 已完成的上下文
{context}

请为当前段落生成 3 个不同的简短样例（每则 2-4 句话，只给切入点或开头示范）。
用户会参考这些样例后自己写出完整段落，所以样例要有启发性但不必写成完稿。

请严格按以下 JSON 格式输出，不要包含任何解释或 Markdown 代码块标记：
{{"examples": ["样例1", "样例2", "样例3"]}}
"""


def _build_example_prompt(state: ComedyState) -> str:
    """构建生成样例的提示词。"""
    outline = (state.plan or {}).get("outline", [])
    section_index = state.current_section
    section_goal = (
        outline[section_index] if section_index < len(outline) else "（无）"
    )

    analysis = state.analysis or {}
    topic = analysis.get("topic", "未指定")
    attitude = analysis.get("attitude", "未指定")
    bias = analysis.get("bias", "未指定")
    emotion = analysis.get("emotion", "未指定")

    style = state.selected_style or state.selected_skill or "默认"

    context_parts: list[str] = []
    if section_index > 0 and state.sections:
        context_parts.append("前文段落：")
        for idx, text in enumerate(state.sections[:section_index], start=1):
            context_parts.append(f"段落 {idx}：{text[:200]}")
    else:
        context_parts.append("（这是第一个段落，无前文）")
    context = "\n".join(context_parts)

    return _EXAMPLES_GENERATION_PROMPT.format(
        section_goal=section_goal,
        topic=topic,
        attitude=attitude,
        bias=bias,
        emotion=emotion,
        style=style,
        context=context,
    )


def _parse_examples(output_text: str) -> list[str]:
    """从模型输出中解析 3 个样例。"""
    text = output_text.strip()
    # 如果输出被 Markdown 代码块包裹，去掉它
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    try:
        data = json.loads(text)
        examples = data.get("examples") if isinstance(data, dict) else data
        if isinstance(examples, list) and examples:
            return [str(ex).strip() for ex in examples[:3]]
    except json.JSONDecodeError:
        logger.warning("样例解析失败，尝试按行拆分: %s", text[:200])

    # 兜底：按空行拆分，取前 3 段
    lines = [line.strip("-• \t") for line in text.splitlines() if line.strip()]
    return lines[:3] if lines else ["（未能生成样例，请直接输入本段内容）"]


def example_generator_node(state: ComedyState, llm: BaseChatModel | None = None) -> dict:
    """为当前段落生成 3 个参考样例。

    Returns:
        dict: section_examples + phase="example_review"
    """
    if llm is None:
        llm = ModelFactory.get_model(state.model, task_type="creative")

    prompt = _build_example_prompt(state)
    try:
        response = llm.invoke([("system", "你是一名中文脱口秀编剧，只输出 JSON。"), ("human", prompt)])
        output_text = str(getattr(response, "content", response)).strip()
        examples = _parse_examples(output_text)
    except Exception as e:
        logger.warning("生成样例失败: %s", e)
        examples = [
            "样例 1：从生活细节切入，带出一个小反差。",
            "样例 2：先承认一个普遍现象，再给出独特观察。",
            "样例 3：用具体场景开场，让观众迅速代入。",
        ]

    # 确保始终有 3 个样例
    while len(examples) < 3:
        examples.append("（样例占位，请直接输入本段内容）")

    return {
        "section_examples": examples[:3],
        "phase": "example_review",
    }


def example_review_node(state: ComedyState) -> dict:
    """展示 3 个样例并等待用户输入当前段落。

    Returns:
        dict: 用户输入写入 sections，phase="reviewing"
    """
    outline = (state.plan or {}).get("outline", [])
    section_index = state.current_section
    section_goal = outline[section_index] if section_index < len(outline) else "（无）"

    interrupt_payload = {
        "message": "请参考下面的 3 个样例，在输入框写出你自己的段落，写完后发送。",
        "section_index": section_index,
        "section_goal": section_goal,
        "section_examples": state.section_examples or [],
    }

    logger.debug("example_review_node interrupt, waiting for user draft")
    user_draft = interrupt(interrupt_payload)
    draft_text = str(user_draft).strip()

    sections = state.sections.copy()
    if section_index < len(sections):
        sections[section_index] = draft_text
    else:
        sections.append(draft_text)

    return {
        "sections": sections,
        "user_draft": draft_text,
        "section_examples": None,
        "feedback": "",
        "phase": "reviewing",
    }
