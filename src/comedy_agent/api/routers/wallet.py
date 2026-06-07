"""钱包与 Token 账户路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user

router = APIRouter(tags=["wallet"])


class WalletResponse(BaseModel):
    """钱包信息响应。"""

    balance: int = Field(description="Token 余额")
    total_consumed: int = Field(description="累计消费")
    total_recharged: int = Field(description="累计充值")


class RechargeRequest(BaseModel):
    """充值请求。"""

    amount: int = Field(description="充值金额", ge=1)


@router.get("/me/wallet", response_model=WalletResponse)
async def get_wallet(user_id: str = Depends(get_current_user)) -> WalletResponse:
    """获取当前用户 Token 账户信息。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    account = state.memory.get_token_account(user_id)
    return WalletResponse(
        balance=account.balance,
        total_consumed=account.total_consumed,
        total_recharged=account.total_recharged,
    )


@router.post("/me/recharge", response_model=WalletResponse)
async def recharge(
    request: RechargeRequest, user_id: str = Depends(get_current_user)
) -> WalletResponse:
    """充值 Token（开发阶段模拟）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    account = state.memory.recharge_tokens(user_id, request.amount)
    return WalletResponse(
        balance=account.balance,
        total_consumed=account.total_consumed,
        total_recharged=account.total_recharged,
    )
