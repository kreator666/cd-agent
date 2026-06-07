"""演员工作台路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user

router = APIRouter(tags=["actor"])


class DashboardResponse(BaseModel):
    """演员数据看板响应。"""

    usage_count: int = Field(description="风格模型本周调用次数")
    estimated_income: int = Field(description="预计分成收益（分）")
    pending_count: int = Field(description="待审核投稿数")


class WithdrawRequest(BaseModel):
    """提现请求。"""

    amount: int = Field(description="提现金额（分）", ge=1)


@router.get("/actor/dashboard", response_model=DashboardResponse)
async def actor_dashboard(user_id: str = Depends(get_current_user)) -> DashboardResponse:
    """演员工作台数据看板。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    # TODO: 根据实际演员身份查询数据，当前返回占位数据
    submissions = state.memory.list_submissions(target_actor=user_id, status="pending")
    return DashboardResponse(
        usage_count=0,
        estimated_income=0,
        pending_count=len(submissions),
    )


@router.get("/actor/earnings")
async def actor_earnings(user_id: str = Depends(get_current_user)) -> dict[str, Any]:
    """演员收益明细。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    records = state.memory.list_earnings(actor_name=user_id)
    return {"earnings": records}


@router.post("/actor/withdraw")
async def actor_withdraw(
    request: WithdrawRequest, user_id: str = Depends(get_current_user)
) -> dict[str, bool]:
    """申请提现。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    # TODO: 接入实际支付系统，当前仅记录提现申请
    from comedy_agent.memory.models import EarningRecordData

    state.memory.save_earning(
        EarningRecordData(
            user_id=user_id,
            record_type="withdrawal",
            amount=-request.amount,
            description="提现申请",
        )
    )
    return {"success": True}
