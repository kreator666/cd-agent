"""润色节点：根据用户当前段落、大纲和上下文进行润色。

用户点击"润色"后调用，输出润色后的段落并回到 human_review。
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.core.config import settings
from comedy_agent.models.factory import ModelConfigError, ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


_POLISH_PROMPT = """你是一名中文脱口秀资深编剧 + 开放麦老演员。你的任务是对用户写的段落进行**升级打磨**，不是小修小补，而是让它更口语、更有节奏、笑点更狠，能够直接上台演。

## 打磨要求（必须执行）

1. **口语化重写**：去掉书面语、作文感、AI 味。句子要像人在台上说话，短、直接、有语气。
2. **节奏紧凑**：删掉“我觉得”“其实”“然后”“就是”等缓冲词，每句都要有信息或笑点。
3. **笑点升级**：找出原文里最有潜力的笑点，再往前推一步。允许使用：
   - 具象化（把抽象情绪变成具体画面）
   - 升级法（把荒谬程度再拉高一级）
   - 突然转向（让观众以为往 A，结果拐到 B）
4. **保留原意，但允许大胆改写**：核心观点和真实经历不能丢，但措辞、顺序、节奏、笑料可以大刀阔斧改。
5. **可见改动**：至少做 3 处明显改动。禁止直接复制原文或只做同义词替换。
6. **贴合四维度与风格**：语气必须符合下面的话题、态度、偏见/视角、情绪和风格。

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

## 用户当前段落
{section_text}

## 额外要求
{feedback}

## 输出规则
- 只输出打磨后的段落正文，不要解释。
- 不要加“## 段子正文”“打磨后”等标题或标签。
- 不要输出分析过程、创作思路、点评。
- 结果必须是连续、干净的纯文本段落，适合演员直接上台表演。

## 参考示例（打磨力度）

原文：现在年轻人上班压力真的很大，每天加班到很晚，领导还总说你不够努力，我感觉挺无奈的，但也只能继续这样。  
打磨后：现在我们上班已经不是被压榨了，是被“ PUA 式压榨”——领导十一点给你发消息：“还没睡呢？年轻人就是要多学习。” 我回他：“领导，我学不动了，再学就该学法医了。”

请按上面的力度打磨用户当前段落。
"""


def polish_node(state: ComedyState, llm: BaseChatModel | None = None) -> dict:
    """润色当前段落。

    Returns:
        dict: sections 更新为润色后的文本，phase="human_review"
    """
    outline = (state.plan or {}).get("outline", [])
    section_index = state.current_section
    section_goal = outline[section_index] if section_index < len(outline) else "（无）"
    section_text = (
        state.sections[section_index]
        if state.sections and section_index < len(state.sections)
        else ""
    )

    analysis = state.analysis or {}
    style = state.selected_style or state.selected_skill or "默认"

    context_parts = []
    if section_index > 0 and state.sections:
        context_parts.append("前文段落：")
        for idx, text in enumerate(state.sections[:section_index], start=1):
            context_parts.append(f"段落 {idx}：{text[:200]}")
    else:
        context_parts.append("（这是第一个段落，无前文）")
    context = "\n".join(context_parts)

    prompt = _POLISH_PROMPT.format(
        section_goal=section_goal,
        topic=analysis.get("topic", "未指定"),
        attitude=analysis.get("attitude", "未指定"),
        bias=analysis.get("bias", "未指定"),
        emotion=analysis.get("emotion", "未指定"),
        style=style,
        context=context,
        section_text=section_text,
        feedback=state.feedback or "无额外要求，请整体润色",
    )

    if llm is None:
        # 优先使用用户显式指定的模型，其次使用 write_node 记录的实际生成模型，
        # 保证润色与生成段子使用同一模型；若该模型不可用，再回退到默认模型。
        model_name = state.model or state.model_used or settings.creative_model
        try:
            llm = ModelFactory.get_model(model_name, task_type="creative")
        except ModelConfigError:
            logger.warning(
                "润色指定的模型 %s 不可用，回退到默认模型 %s",
                model_name,
                settings.default_model,
            )
            llm = ModelFactory.get_model(settings.default_model)

    try:
        response = llm.invoke(
            [
                (
                    "system",
                    "你是中文脱口秀资深编辑。你只输出打磨后的段落正文。打磨必须肉眼可见：口语化、节奏紧凑、笑点升级，禁止原文照搬或只做同义词替换。",
                ),
                ("human", prompt),
            ]
        )
        polished = str(getattr(response, "content", response)).strip()
    except Exception as e:
        logger.warning("润色失败: %s", e)
        polished = section_text

    sections = state.sections.copy()
    if section_index < len(sections):
        sections[section_index] = polished
    else:
        sections.append(polished)

    return {
        "sections": sections,
        "feedback": "",
        "suggestions": None,
        "phase": "human_review",
    }
