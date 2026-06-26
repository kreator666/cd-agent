"""专业版 B 接口：复用 pro.html 的 UI，后端接入 v4 LangGraph StateGraph。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, Field

from comedy_agent.api.billing import charge_model_usage, start_usage_tracking
from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.state.schema import ComedyState

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

    字段与 `pro.html` 前端渲染逻辑对齐，便于直接复用现有 UI。
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
    """从 LangGraph 中断结果中提取段落文本。"""
    default = {"section_text": "", "message": "请审阅当前段落并提供反馈"}
    interrupts = raw.get("__interrupt__")
    if not interrupts:
        return default
    value = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
    if isinstance(value, dict):
        return {
            "section_text": value.get("section_text", ""),
            "message": value.get("message", default["message"]),
        }
    return {**default, "section_text": str(value)}


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
    )


def _build_response(raw: dict | ComedyState, session_id: str) -> ProChatV4Response:
    """将 v4 Graph 输出封装为前端可渲染的 ProChatResponse。"""
    # 处理 interrupt（人类审阅等待）
    if isinstance(raw, dict) and "__interrupt__" in raw:
        info = _extract_interrupt_info(raw)
        section_text = info["section_text"]
        content = (
            f"{info['message']}\n\n{section_text}"
            if section_text
            else info["message"]
        )
        return _build_guide_response(
            session_id=session_id,
            content=content,
            workflow_state="human_review",
            current_role="reviewer",
            next_role="用户",
            next_actions=[
                {"label": "✅ 通过", "action": "approve", "value": "通过"},
                {"label": "✏️ 修改", "action": "modify", "value": "修改"},
                {"label": "🔄 重写", "action": "rewrite", "value": "重写"},
            ],
            steps=[
                {
                    "type": "guide",
                    "content": content,
                    "current_role": "reviewer",
                    "todo_board": [],
                    "next_actions": [
                        {"label": "通过", "action": "approve", "value": "通过"},
                        {"label": "修改", "action": "modify", "value": "修改"},
                    ],
                }
            ],
            artifacts=[
                Artifact(
                    id=f"{session_id}-section",
                    type="section",
                    title="当前段落",
                    content=section_text,
                    created_by="writer",
                )
            ]
            if section_text
            else None,
        )

    # 正常完成状态
    if isinstance(raw, dict):
        graph_state = ComedyState.model_validate(raw)
    else:
        graph_state = raw

    output = graph_state.output or "（无输出）"
    is_script = graph_state.phase == "complete" and output and output != "（未生成内容）"

    if is_script:
        return ProChatV4Response(
            session_id=session_id,
            type="final_script",
            content=output,
            workflow_state="complete",
            skill_name="writer",
            current_role="writer",
            next_role=None,
            steps=[
                {
                    "type": "final_script",
                    "content": output,
                    "current_role": "writer",
                }
            ],
            artifacts=[
                Artifact(
                    id=f"{session_id}-script",
                    type="script",
                    title="最终剧本",
                    content=output,
                    created_by="writer",
                )
            ],
            slots=_analysis_to_slots(graph_state.analysis),
        )

    # chat / search 等其它完成态
    return _build_guide_response(
        session_id=session_id,
        content=output,
        workflow_state=graph_state.phase,
        current_role="喜剧龙虾",
        next_role="用户",
        steps=[{"type": "skill_output", "content": output, "current_role": "喜剧龙虾"}],
        slots=_analysis_to_slots(graph_state.analysis),
    )


def _analysis_to_slots(analysis: dict[str, Any] | None) -> dict[str, Any] | None:
    """将 v4 analysis 映射为 pro 前端的 slots 字段。"""
    if not analysis:
        return None
    slots: dict[str, Any] = {}
    for key in ("topic", "attitude", "bias", "emotion"):
        value = analysis.get(key)
        if value:
            slots[key] = value
    return slots or None


# ------------------------------------------------------------------ #
# API 端点
# ------------------------------------------------------------------ #
@router.post("/chat-v4", response_model=ProChatV4Response)
async def pro_chat_v4(
    request: ProChatV4Request,
    user_id: str = Depends(get_current_user),
) -> ProChatV4Response:
    """专业版 B 对话入口。

    复用 pro.html 的 UI，后端调用 v4 LangGraph StateGraph。
    """
    if state.graph is None:
        raise HTTPException(status_code=503, detail="Graph 未就绪")

    session_id = request.session_id or uuid.uuid4().hex[:16]
    config = {"configurable": {"thread_id": session_id}}

    start_usage_tracking()

    try:
        # 查看当前 checkpoint 状态：若处于人类审阅阶段，则将用户输入作为 feedback 恢复
        current = state.graph.get_state(config)
        phase = current.values.get("phase") if current and current.values else "idle"
        in_review = phase in ("human_review", "routing_feedback")
        is_feedback = in_review and _is_feedback_message(request.message)

        if is_feedback:
            raw_result = await state.graph.ainvoke(
                Command(resume=request.message),
                config=config,
            )
        else:
            raw_result = await state.graph.ainvoke(
                ComedyState(
                    user_input=request.message,
                    model=request.model,
                    user_id=user_id,
                    session_id=session_id,
                ),
                config=config,
            )

        response = _build_response(raw_result, session_id)

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
