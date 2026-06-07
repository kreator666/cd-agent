"""加点盐路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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

    cost = SALT_COST.get(request.salt_level, 20)
    account = state.memory.get_token_account(user_id)
    if account.balance < cost:
        raise HTTPException(
            status_code=402,
            detail=f"Token 余额不足（需 {cost}，余 {account.balance}）",
        )

    level_desc = {
        "light": "约10%",
        "medium": "约20%",
        "heavy": "约30%",
    }.get(request.salt_level, "约20%")

    prompt = (
        f"请对以下文本进行幽默润色，不改变原意，幽默程度{level_desc}：\n\n{request.text}"
    )

    result = state.orch.run(prompt, user_id=user_id)
    polished = result.get("output", "")

    state.memory.deduct_tokens(user_id, cost)
    state.memory.save_salt_history(
        SaltHistoryData(
            user_id=user_id,
            project_id=request.project_id,
            original_text=request.text,
            polished_text=polished,
            salt_level=request.salt_level,
            token_cost=cost,
        )
    )

    return SaltResponse(original=request.text, polished=polished, token_cost=cost)


@router.get("/salt/history")
async def salt_history(user_id: str = Depends(get_current_user)) -> list[dict]:
    """获取当前用户的加点盐历史。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    histories = state.memory.list_salt_history(user_id)
    return [
        {
            "salt_id": h.salt_id,
            "original_text": h.original_text,
            "polished_text": h.polished_text,
            "salt_level": h.salt_level,
            "token_cost": h.token_cost,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in histories
    ]
