"""专业版 B 接口：供 pro-b.html 使用，后端接入 v4 LangGraph StateGraph。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from comedy_agent.api.billing import charge_model_usage, start_usage_tracking
from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.state.schema import ComedyState
from comedy_agent.utils.messages import dicts_to_messages, messages_to_dicts
from comedy_agent.utils.summarizer import summarize_messages

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pro", tags=["pro-v4"])


# ------------------------------------------------------------------ #
# 请求 / 响应模型
# ------------------------------------------------------------------ #
class ProChatV4Request(BaseModel):
    """专业版 B 对话请求。"""

    session_id: str | None = Field(default=None, description="会话 ID，为空则新建")
    message: str = Field(description="用户消息")
    outline: str | None = Field(default=None, description="选题大纲（兼容旧字段，暂不启用）")
    persona_id: str | None = Field(default=None, description="人物画像 ID（暂不启用）")
    skill_id: str | None = Field(default=None, description="选中的写作 Skill ID")
    style: str | None = Field(default=None, description="选中的风格子选项")
    writing_mode: str | None = Field(default=None, description="写作模式：sample_guide / direct_writer / coach")
    model: str | None = Field(default=None, description="使用的模型名称")


class Artifact(BaseModel):
    """工作台内容单元。"""

    id: str = Field(description="artifact 唯一 ID")
    type: str = Field(description="类型：outline / research / script / review / section")
    title: str = Field(description="标题")
    content: str = Field(description="内容")
    op: str = Field(default="create", description="操作：create / append / update")
    version: int = Field(default=1, description="版本号")
    created_by: str = Field(description="生成该内容的角色名")


class ProChatV4Response(BaseModel):
    """专业版 B 对话响应。

    字段与 `pro-b.html` 前端渲染逻辑对齐。
    """

    session_id: str = Field(description="会话 ID")
    type: str = Field(description="响应类型：guide / skill_output / final_script / error")
    content: str = Field(description="响应内容")
    workflow_state: str = Field(default="idle", description="当前工作流状态")
    skill_name: str | None = Field(default=None, description="当前调用的 Skill/Worker 名称")
    current_role: str | None = Field(default=None, description="当前发言角色")
    next_role: str | None = Field(default=None, description="下一个该发言的角色")
    next_actions: list[dict[str, Any]] | None = Field(
        default=None, description="下一步可执行操作"
    )
    steps: list[dict[str, Any]] | None = Field(
        default=None, description="链式执行的所有步骤"
    )
    slots: dict[str, Any] | None = Field(default=None, description="当前已收集的槽位")
    skill_meta: dict[str, Any] | None = Field(
        default=None, description="当前 Skill/写作元信息（如风格、检索示例数）"
    )
    artifacts: list[Artifact] | None = Field(default=None, description="工作台内容更新")


# ------------------------------------------------------------------ #
# 辅助函数
# ------------------------------------------------------------------ #
def _is_feedback_message(message: str) -> bool:
    """判断用户消息是否为审阅反馈。"""
    lowered = message.strip().lower()
    feedback_keywords = ("通过", "继续", "next", "ok", "yes", "y", "修改", "重写")
    return any(kw in lowered for kw in feedback_keywords) or lowered.startswith("通过")


def _extract_interrupt_info(raw: dict) -> dict[str, Any]:
    """从 LangGraph 中断结果中提取计划审阅或段落审阅信息。"""
    section_default = {
        "review_type": "section",
        "section_text": "",
        "message": "请审阅当前段落并提供反馈",
    }
    interrupts = raw.get("__interrupt__")
    if not interrupts:
        return section_default
    value = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
    if not isinstance(value, dict):
        return {**section_default, "section_text": str(value)}

    # 计划审阅：payload 里包含 outline
    if "outline" in value:
        return {
            "review_type": "plan",
            "message": value.get("message", "计划已生成，请确认或调整"),
            "todo": value.get("todo", []),
            "outline": value.get("outline", []),
            "tone": value.get("tone", ""),
        }

    # 样例引导写作：payload 里包含 section_examples
    if "section_examples" in value:
        return {
            "review_type": "example_review",
            "section_index": value.get("section_index", 0),
            "section_goal": value.get("section_goal", ""),
            "section_examples": value.get("section_examples", []),
            "message": value.get("message", "请参考样例撰写当前段落"),
        }

    # 教练模式草稿收集：payload 里包含 coaching_hints
    if "coaching_hints" in value:
        return {
            "review_type": "drafting",
            "section_index": value.get("section_index", 0),
            "section_goal": value.get("section_goal", ""),
            "coaching_hints": value.get("coaching_hints", ""),
            "message": value.get("message", "请根据教练提示撰写当前段落"),
        }

    return {
        "review_type": "section",
        "section_index": value.get("section_index", 0),
        "section_text": value.get("section_text", ""),
        "message": value.get("message", section_default["message"]),
        "suggestions": value.get("suggestions", ""),
    }


def _format_plan_review_content(
    message: str,
    slots: dict[str, Any] | None,
    todo: list[str],
    outline: list[str],
    tone: str,
) -> str:
    """把 Planner 输出汇总为给用户的结构化反馈文本。"""
    parts = [f"给用户的反馈：{message}", "", "当前处于什么状态："]

    if slots:
        for cn in ("话题", "态度", "偏见", "情绪"):
            if slots.get(cn):
                parts.append(f"• {cn}：{slots[cn]}")
    if tone:
        parts.append(f"• 整体语气：{tone}")

    if todo:
        parts.extend(["", "待办事项："] + [f"{i}. {t}" for i, t in enumerate(todo, 1)])
    if outline:
        parts.extend(["", "段落大纲："] + [f"{i}. {t}" for i, t in enumerate(outline, 1)])

    parts.extend(
        [
            "",
            "提示用户应该做什么：点击 A 开始写作，B 重新规划，C 修改计划（或直接输入修改意见）。",
        ]
    )
    return "\n".join(parts)


def _build_guide_response(
    session_id: str,
    content: str,
    workflow_state: str = "guide",
    current_role: str = "喜剧龙虾",
    next_role: str | None = "用户",
    next_actions: list[dict[str, Any]] | None = None,
    steps: list[dict[str, Any]] | None = None,
    artifacts: list[Artifact] | None = None,
    slots: dict[str, Any] | None = None,
    skill_meta: dict[str, Any] | None = None,
) -> ProChatV4Response:
    """构造 guide 类型响应。"""
    return ProChatV4Response(
        session_id=session_id,
        type="guide",
        content=content,
        workflow_state=workflow_state,
        current_role=current_role,
        next_role=next_role,
        next_actions=next_actions or [],
        steps=steps or [],
        artifacts=artifacts,
        slots=slots,
        skill_meta=skill_meta,
    )


def _build_response(raw: dict | ComedyState, session_id: str) -> ProChatV4Response:
    """将 v4 Graph 输出封装为前端可渲染的 ProChatResponse。"""
    # 处理 interrupt（计划审阅 / 人类审阅等待）
    if isinstance(raw, dict) and "__interrupt__" in raw:
        info = _extract_interrupt_info(raw)

        if info.get("review_type") == "plan":
            slots = _merge_slots(
                raw.get("slots") if isinstance(raw, dict) else None,
                raw.get("analysis") if isinstance(raw, dict) else None,
            )
            # 从 plan 中提取知识引用，供前端展示
            plan_data = raw.get("plan") if isinstance(raw, dict) else {}
            plan_knowledge_refs = plan_data.get("knowledge_references") if isinstance(plan_data, dict) else None
            plan_skill_meta = raw.get("skill_meta") if isinstance(raw, dict) else None
            if plan_skill_meta:
                plan_skill_meta = dict(plan_skill_meta)
                if plan_knowledge_refs and "knowledge_references" not in plan_skill_meta:
                    plan_skill_meta["knowledge_references"] = plan_knowledge_refs
            else:
                plan_skill_meta = {"knowledge_references": plan_knowledge_refs} if plan_knowledge_refs else None
            content = _format_plan_review_content(
                info["message"],
                slots,
                info.get("todo", []),
                info.get("outline", []),
                info.get("tone", ""),
            )
            return _build_guide_response(
                session_id=session_id,
                content=content,
                workflow_state="plan_review",
                current_role="planner",
                next_role="用户",
                next_actions=[
                    {"label": "A. 开始写作", "action": "approve_plan", "value": "开始写作"},
                    {"label": "B. 重新规划", "action": "replan", "value": "重新规划"},
                    {"label": "C. 修改计划", "action": "modify_plan", "value": "修改计划"},
                ],
                steps=[
                    {
                        "type": "guide",
                        "content": content,
                        "current_role": "planner",
                        "todo_board": [],
                        "next_actions": [
                            {"label": "A. 开始写作", "action": "approve_plan", "value": "开始写作"},
                            {"label": "B. 重新规划", "action": "replan", "value": "重新规划"},
                            {"label": "C. 修改计划", "action": "modify_plan", "value": "修改计划"},
                        ],
                    }
                ],
                artifacts=[
                    Artifact(
                        id=f"{session_id}-outline",
                        type="outline",
                        title="创作计划",
                        content="\n".join(
                            [f"{i}. {t}" for i, t in enumerate(info.get("outline", []), 1)]
                        ),
                        created_by="planner",
                    )
                ]
                if info.get("outline")
                else None,
                skill_meta=plan_skill_meta,
            )

        if info.get("review_type") == "drafting":
            section_index = info.get("section_index", 0)
            section_label = f"第 {section_index + 1} 段"
            coaching_hints = info.get("coaching_hints", "")
            message = info.get("message", "请根据教练提示撰写当前段落")
            content = f"{message}\n\n{coaching_hints}".strip()
            return _build_guide_response(
                session_id=session_id,
                content=content,
                workflow_state="drafting",
                current_role="写稿教练",
                next_role="用户",
                next_actions=[
                    {"label": "📝 提交草稿", "action": "submit_draft", "value": "提交草稿"},
                ],
                steps=[
                    {
                        "type": "guide",
                        "content": content,
                        "current_role": "写稿教练",
                        "todo_board": [],
                        "next_actions": [
                            {"label": "提交草稿", "action": "submit_draft", "value": "提交草稿"},
                        ],
                    }
                ],
                artifacts=None,
                skill_meta=raw.get("skill_meta") if isinstance(raw, dict) else None,
            )

        if info.get("review_type") == "example_review":
            section_index = info.get("section_index", 0)
            section_label = f"第 {section_index + 1} 段"
            section_goal = info.get("section_goal", "")
            section_examples = info.get("section_examples", []) or []
            message = info.get("message", "请参考样例撰写当前段落")
            examples_text = "\n\n".join(
                [f"样例 {i + 1}：\n{ex}" for i, ex in enumerate(section_examples)]
            )
            content = f"{message}\n\n段落目标：{section_goal}\n\n{examples_text}".strip()
            return _build_guide_response(
                session_id=session_id,
                content=content,
                workflow_state="example_review",
                current_role="写手阿文",
                next_role="用户",
                next_actions=[
                    {"label": "📝 提交本段", "action": "submit_section", "value": "提交本段"},
                ],
                steps=[
                    {
                        "type": "guide",
                        "content": content,
                        "current_role": "写手阿文",
                        "todo_board": [],
                        "next_actions": [
                            {"label": "提交本段", "action": "submit_section", "value": "提交本段"},
                        ],
                    }
                ],
                artifacts=None,
                skill_meta=raw.get("skill_meta") if isinstance(raw, dict) else None,
            )

        section_text = info["section_text"]
        section_index = info.get("section_index", 0)
        section_label = f"第 {section_index + 1} 段"
        suggestions = info.get("suggestions", "")
        content = (
            f"{info['message']}\n\n{section_text}"
            if section_text
            else info["message"]
        )
        if suggestions:
            content = f"{content}\n\n💡 改进建议：\n{suggestions}"
        return _build_guide_response(
            session_id=session_id,
            content=content,
            workflow_state="human_review",
            current_role="写手阿文",
            next_role="用户",
            next_actions=[
                {"label": "✅ 通过", "action": "approve", "value": "通过"},
                {"label": "✏️ 修改", "action": "modify", "value": "修改"},
                {"label": "✨ 润色", "action": "polish", "value": "润色"},
                {"label": "💡 给出建议", "action": "suggest", "value": "给出建议"},
            ],
            steps=[
                {
                    "type": "guide",
                    "content": content,
                    "current_role": "写手阿文",
                    "todo_board": [],
                    "next_actions": [
                        {"label": "通过", "action": "approve", "value": "通过"},
                        {"label": "修改", "action": "modify", "value": "修改"},
                        {"label": "润色", "action": "polish", "value": "润色"},
                        {"label": "给出建议", "action": "suggest", "value": "给出建议"},
                    ],
                }
            ],
            artifacts=[
                Artifact(
                    id=f"{session_id}-section-{section_index}",
                    type="section",
                    title=section_label,
                    content=section_text,
                    created_by="writer",
                )
            ]
            if section_text
            else None,
            skill_meta=raw.get("skill_meta") if isinstance(raw, dict) else None,
        )

    # 正常完成状态
    if isinstance(raw, dict):
        graph_state = ComedyState.model_validate(raw)
    else:
        graph_state = raw

    output = graph_state.output or "（无输出）"
    response_type = graph_state.response_type

    # 默认兜底：未设置 response_type 的 complete + 有输出，按 script 处理
    is_script = (
        graph_state.phase == "complete"
        and response_type == "script"
    ) or (
        graph_state.phase == "complete"
        and response_type is None
        and output
        and output != "（未生成内容）"
        and output != "（无输出）"
    )

    slots = _merge_slots(graph_state.slots, graph_state.analysis)

    if is_script:
        return ProChatV4Response(
            session_id=session_id,
            type="final_script",
            content=output,
            workflow_state="complete",
            skill_name="chief_editor",
            current_role="总编",
            next_role=None,
            steps=[
                {
                    "type": "final_script",
                    "content": output,
                    "current_role": "总编",
                }
            ],
            artifacts=[
                Artifact(
                    id=f"{session_id}-script",
                    type="script",
                    title="最终剧本",
                    content=output,
                    created_by="总编",
                )
            ],
            slots=slots,
            skill_meta=graph_state.skill_meta,
        )

    # guide / error / 其它完成态
    return _build_guide_response(
        session_id=session_id,
        content=output,
        workflow_state=graph_state.phase,
        current_role="喜剧龙虾",
        next_role="用户",
        next_actions=graph_state.suggested_actions or [],
        steps=[{"type": "guide", "content": output, "current_role": "喜剧龙虾"}],
        slots=slots,
        skill_meta=graph_state.skill_meta,
    )


def _merge_slots(
    slots: dict[str, str] | None, analysis: dict[str, Any] | None
) -> dict[str, Any] | None:
    """合并 state.slots（中文）与 analysis（英文）为前端可用的 slots。"""
    result: dict[str, Any] = {}
    if slots:
        result.update(slots)
    if analysis:
        mapping = {
            "topic": "话题",
            "attitude": "态度",
            "bias": "偏见",
            "emotion": "情绪",
        }
        for en, cn in mapping.items():
            value = analysis.get(en)
            if value and cn not in result:
                result[cn] = value
    return result or None


# ------------------------------------------------------------------ #
# API 端点
# ------------------------------------------------------------------ #
@router.post("/chat-v4", response_model=ProChatV4Response)
async def pro_chat_v4(
    request: ProChatV4Request,
    user_id: str = Depends(get_current_user),
) -> ProChatV4Response:
    """专业版 B 对话入口。

    供 pro-b.html 调用，后端接入 v4 LangGraph StateGraph。
    """
    if state.graph is None:
        raise HTTPException(status_code=503, detail="Graph 未就绪")

    session_id = request.session_id or uuid.uuid4().hex[:16]
    config = {"configurable": {"thread_id": session_id}}

    start_usage_tracking()

    try:
        # 查看当前 checkpoint 状态：若处于计划审阅/人类审阅阶段，则将用户输入作为 feedback 恢复
        current = state.graph.get_state(config)
        phase = current.values.get("phase") if current and current.values else "idle"

        if phase in ("plan_review", "human_review", "drafting", "example_review"):
            # 计划审阅/段落审阅/教练草稿阶段：任何用户输入都视为反馈/草稿（支持 [manual] 人工编辑）
            is_feedback = True
        elif phase == "routing_feedback":
            is_feedback = _is_feedback_message(request.message)
        else:
            is_feedback = False

        state_updates: dict[str, Any] = {}
        if request.skill_id:
            state_updates["selected_skill"] = request.skill_id
        if request.style:
            state_updates["selected_style"] = request.style
        if request.writing_mode in ("sample_guide", "direct_writer", "coach"):
            state_updates["manual_section_mode"] = request.writing_mode == "sample_guide"

        if is_feedback:
            raw_result = await state.graph.ainvoke(
                Command(
                    resume=request.message,
                    update=state_updates if state_updates else None,
                ),
                config=config,
            )
        else:
            # 读取 checkpoint 中的历史状态，避免用默认值覆盖 slots/analysis/plan
            current = state.graph.get_state(config)
            prev_values = (current.values or {}) if current else {}

            # checkpoint 为空时，尝试从持久化 memory 加载历史消息
            history_messages: list[Any] = []
            if not prev_values and state.memory is not None:
                try:
                    conv = state.memory.load_conversation(user_id, session_id)
                    if conv:
                        if conv.messages:
                            history_messages = dicts_to_messages(conv.messages)
                        if conv.summary:
                            prev_values["conversation_summary"] = conv.summary
                        if conv.slot_conversations:
                            prev_values["slot_conversations"] = {
                                dim: dicts_to_messages(msgs)
                                for dim, msgs in conv.slot_conversations.items()
                            }
                except Exception:
                    logger.debug("从 memory 加载会话历史失败", exc_info=True)

            # 构造本轮传入图的消息链：checkpoint 历史由 LangGraph 自动合并，
            # 仅当 checkpoint 为空且从 memory 回填时才把历史一并传入，避免重复
            messages_for_graph = history_messages + [HumanMessage(content=request.message)]

            # 计算完整历史长度（checkpoint 历史 + 当前输入），用于判断是否触发摘要
            checkpoint_messages = prev_values.get("messages") or []
            total_history = list(checkpoint_messages) + [HumanMessage(content=request.message)]

            # 若历史消息过长且尚无摘要，生成对话摘要以保留早期关键信息
            if len(total_history) > 20 and not prev_values.get("conversation_summary"):
                try:
                    summary = await summarize_messages(total_history, model=request.model)
                    if summary:
                        prev_values["conversation_summary"] = summary
                except Exception:
                    logger.debug("生成对话摘要失败", exc_info=True)

            # 新一轮创作请求开始时，清理上一轮已完成的 analysis / plan，避免旧计划被复用
            is_new_creation = prev_values.get("phase") == "complete" or any(
                kw in request.message for kw in ("开始创作", "出大纲", "生成计划", "写大纲")
            )
            if is_new_creation:
                prev_values.pop("analysis", None)
                prev_values.pop("plan", None)

            # 把当前系统可用能力注入状态，供 GuideAgent 在咨询时列举
            available_skills: list[str] = []
            if state.orch is not None:
                try:
                    available_skills = [
                        s.get("name", "") for s in state.orch.list_skills() if s.get("name")
                    ]
                except Exception:
                    available_skills = []

            merged_state = {
                **prev_values,
                # 重置 phase 为 idle，让 Supervisor 从 START 重新调度，否则上一轮 complete 会直接结束
                "phase": "idle",
                "user_input": request.message,
                "model": request.model,
                "messages": messages_for_graph,
                "session_id": session_id,
                "user_id": user_id,
                "available_skills": available_skills,
                **state_updates,
            }
            raw_result = await state.graph.ainvoke(
                ComedyState(**merged_state),
                config=config,
            )

        response = _build_response(raw_result, session_id)

        # 把本轮 AI 回复追加到 checkpoint，供下一轮 Context Analyzer / Planner 读取
        try:
            ai_message = AIMessage(content=response.content)
            state.graph.update_state(
                config,
                {"messages": [ai_message]},
            )

            # 同时把 AI 回复归档到当前活跃维度的独立对话历史中
            current_values = state.graph.get_state(config)
            if current_values and current_values.values:
                active_dim = current_values.values.get("active_slot_dimension")
                if active_dim:
                    state.graph.update_state(
                        config,
                        {"slot_conversations": {active_dim: [ai_message]}},
                    )
        except Exception:
            logger.debug("追加 AI 消息到 checkpoint 失败，继续返回响应", exc_info=True)

        # 把完整对话保存到持久化 memory，供 checkpoint 丢失或服务重启后恢复
        try:
            final_state = state.graph.get_state(config)
            if final_state and final_state.values and state.memory is not None:
                msgs = final_state.values.get("messages") or []
                slot_conversations = final_state.values.get("slot_conversations") or {}
                state.memory.save_conversation(
                    user_id=user_id,
                    session_id=session_id,
                    messages=messages_to_dicts(msgs),
                    summary=response.content[:80] if response.content else None,
                    source="pro_v4",
                    slot_conversations={
                        dim: messages_to_dicts(msgs)
                        for dim, msgs in slot_conversations.items()
                    },
                )
        except Exception:
            logger.debug("保存会话到 memory 失败", exc_info=True)

        charge_model_usage(
            user_id=user_id,
            endpoint="/pro/chat-v4",
            description="专业版 B 对话（v4 Graph）",
            session_id=session_id,
            fallback_cost=5,
        )
        return response
    except Exception as e:
        logger.exception("专业版 B /pro/chat-v4 处理失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat-v4/{session_id}", response_model=ProChatV4Response)
async def pro_chat_v4_load(
    session_id: str,
    user_id: str = Depends(get_current_user),
) -> ProChatV4Response:
    """加载专业版 B 会话状态（用于前端恢复历史对话）。"""
    if state.graph is None:
        raise HTTPException(status_code=503, detail="Graph 未就绪")

    config = {"configurable": {"thread_id": session_id}}
    current = state.graph.get_state(config)
    if not current or not current.values:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    return _build_response(current.values, session_id)
