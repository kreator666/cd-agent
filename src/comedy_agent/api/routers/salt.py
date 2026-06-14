"""加点盐路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.billing import charge_model_usage, start_usage_tracking
from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.memory.models import SaltHistoryData

router = APIRouter(tags=["salt"])

SALT_COST = {"light": 10, "medium": 20, "heavy": 30}


class SaltRequest(BaseModel):
    """加点盐请求。"""

    text: str = Field(description="原始文本")
    salt_level: str = Field(default="medium", description="盐度：light / medium / heavy")
    project_id: str | None = Field(default=None, description="关联项目 ID")
    model: str | None = Field(default=None, description="使用的模型名称")


class SaltResponse(BaseModel):
    """加点盐响应。"""

    original: str = Field(description="原始文本")
    polished: str = Field(description="润色后文本")
    token_cost: int = Field(description="消耗 Token 数")


@router.post("/salt", response_model=SaltResponse)
async def salt(request: SaltRequest, user_id: str = Depends(get_current_user)) -> SaltResponse:
    """给日常文本加一点幽默，不改变原意。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    min_cost = SALT_COST.get(request.salt_level, 20)
    account = state.memory.get_token_account(user_id)
    if account.balance < min_cost:
        raise HTTPException(
            status_code=402,
            detail=f"Token 余额不足（至少需 {min_cost}，余 {account.balance}）",
        )

    if request.model:
        state.orch.set_model(request.model)

    # 通过 skill 指令明确调用 add_salt，走 orchestrator/agent 路由
    prompt = (
        f"使用 add_salt 技能 来对以下文本进行幽默润色。\n\n"
        f"原文：{request.text}\n"
        f"盐度：{request.salt_level}"
    )
    start_usage_tracking()
    result = state.orch.run(prompt, user_id=user_id)
    polished = result.get("output", "")

    billing = charge_model_usage(
        user_id=user_id,
        endpoint="/salt",
        description=f"加点盐 ({request.salt_level})",
        fallback_cost=min_cost,
    )
    cost = billing["cost"]
    # 统一保存到 conversation，source="salt"
    import uuid
    session_id = uuid.uuid4().hex[:16]
    state.memory.save_conversation(
        user_id=user_id,
        session_id=session_id,
        messages=[
            {"role": "human", "content": request.text},
            {"role": "ai", "content": polished},
        ],
        summary=(request.text[:40] + "… [加点盐]") if len(request.text) > 40 else (request.text + " [加点盐]"),
        source="salt",
        metadata={
            "salt_level": request.salt_level,
            "original_text": request.text,
            "polished_text": polished,
            "token_cost": cost,
            "project_id": request.project_id,
        },
    )

    return SaltResponse(original=request.text, polished=polished, token_cost=cost)


@router.get("/salt/history")
async def salt_history(user_id: str = Depends(get_current_user)) -> list[dict]:
    """获取当前用户的加点盐历史（从统一 conversation 中过滤）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    conversations = state.memory.list_conversations(user_id, limit=100)
    salt_convs = [c for c in conversations if c.source == "salt"]
    return [
        {
            "salt_id": c.session_id,
            "original_text": c.metadata.get("original_text", "") if c.metadata else "",
            "polished_text": c.metadata.get("polished_text", "") if c.metadata else "",
            "salt_level": c.metadata.get("salt_level", "") if c.metadata else "",
            "token_cost": c.metadata.get("token_cost", 0) if c.metadata else 0,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in salt_convs
    ]
