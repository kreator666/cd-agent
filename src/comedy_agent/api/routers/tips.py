"""打赏与提现路由。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.core.config import settings
from comedy_agent.memory.models import EarningRecordData, TipRecordData, WithdrawalRequestData

router = APIRouter(prefix="/tips", tags=["tips"])


class CreateTipIntentRequest(BaseModel):
    """创建打赏意图请求。"""

    result_id: str = Field(description="广场段子 result_id")
    amount_cents: int = Field(ge=1, description="打赏金额（美分）")
    currency: str = Field(default="usd", description="币种")


class CreateTipIntentResponse(BaseModel):
    """创建打赏意图响应。"""

    tip_id: str = Field(description="打赏意图 ID")
    payment_url: str = Field(description="Anyway 支付链接")


class EarningsResponse(BaseModel):
    """作者收益概览响应。"""

    total_cents: int = Field(description="累计收益（美分）")
    withdrawn_cents: int = Field(description="已提现（美分）")
    pending_cents: int = Field(description="可提现（美分）")
    currency: str = Field(description="币种")


class WithdrawalRequestBody(BaseModel):
    """提现申请请求。"""

    amount_cents: int = Field(ge=1, description="提现金额（美分）")
    payout_method: str = Field(description="wechat / alipay / bank")
    payout_account: str = Field(description="收款账号")


class WithdrawalResponse(BaseModel):
    """提现申请响应。"""

    request_id: str = Field(description="申请 ID")
    amount_cents: int = Field(description="提现金额（美分）")
    status: str = Field(description="申请状态")
    payout_method: str | None = Field(default=None, description="收款方式")
    payout_account: str | None = Field(default=None, description="收款账号")
    created_at: str | None = Field(default=None, description="申请时间")


class TipRecordItem(BaseModel):
    """打赏记录项。"""

    tip_id: str
    author_id: str
    result_id: str
    payer_user_id: str | None
    amount_cents: int
    currency: str
    status: str
    fee_cents: int
    net_amount_cents: int
    created_at: str | None
    paid_at: str | None


@router.post("/intent", response_model=CreateTipIntentResponse)
async def create_tip_intent(
    request: CreateTipIntentRequest,
    user_id: str = Depends(get_current_user),
) -> CreateTipIntentResponse:
    """创建 Anyway 打赏意图并返回支付链接。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    if not settings.anyway_payment_link_url:
        raise HTTPException(status_code=503, detail="Anyway payment link 未配置")

    if request.amount_cents < settings.anyway_min_tip_cents:
        raise HTTPException(status_code=400, detail=f"打赏金额不能低于 {settings.anyway_min_tip_cents} 美分")
    if request.amount_cents > settings.anyway_max_tip_cents:
        raise HTTPException(status_code=400, detail=f"打赏金额不能高于 {settings.anyway_max_tip_cents} 美分")

    # 查询广场段子及作者
    result = state.memory.get_eval_result(request.result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="段子不存在或未发布")

    author_id = getattr(result, "user_id", None)
    if not author_id:
        raise HTTPException(status_code=404, detail="无法确定作者")
    if author_id == user_id:
        raise HTTPException(status_code=400, detail="不能给自己打赏")

    fee_cents = int(request.amount_cents * settings.anyway_fee_percent / 100)
    net_amount_cents = request.amount_cents - fee_cents
    tip_id = "tip_" + uuid.uuid4().hex[:16]
    merchant_reference = tip_id

    metadata: dict[str, Any] = {
        "result_id": request.result_id,
        "author_id": author_id,
    }
    if user_id:
        metadata["payer_user_id"] = user_id

    record = TipRecordData(
        tip_id=tip_id,
        author_id=author_id,
        result_id=request.result_id,
        payer_user_id=user_id,
        amount_cents=request.amount_cents,
        currency=request.currency,
        status="pending",
        merchant_reference=merchant_reference,
        metadata_json=metadata,
        fee_cents=fee_cents,
        net_amount_cents=net_amount_cents,
    )
    state.memory.create_tip_record(record)

    payment_url = (
        f"{settings.anyway_payment_link_url}?"
        f"merchant_reference={merchant_reference}&"
        f"author_id={author_id}&"
        f"result_id={request.result_id}"
    )
    if user_id:
        payment_url += f"&payer_user_id={user_id}"

    return CreateTipIntentResponse(tip_id=tip_id, payment_url=payment_url)


@router.get("/earnings", response_model=EarningsResponse)
async def get_earnings(user_id: str = Depends(get_current_user)) -> EarningsResponse:
    """获取当前登录作者的收益概览。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    summary = state.memory.get_author_earnings(user_id)
    return EarningsResponse(
        total_cents=summary["total_cents"],
        withdrawn_cents=summary["withdrawn_cents"],
        pending_cents=summary["pending_cents"],
        currency=summary["currency"],
    )


@router.get("/history", response_model=list[TipRecordItem])
async def list_tip_history(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[TipRecordItem]:
    """获取当前登录作者的打赏记录。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    records = state.memory.list_tip_records(
        author_id=user_id, status=status, limit=limit, offset=offset
    )
    return [
        TipRecordItem(
            tip_id=r.tip_id,
            author_id=r.author_id,
            result_id=r.result_id,
            payer_user_id=r.payer_user_id,
            amount_cents=r.amount_cents,
            currency=r.currency,
            status=r.status,
            fee_cents=r.fee_cents,
            net_amount_cents=r.net_amount_cents,
            created_at=r.created_at.isoformat() if r.created_at else None,
            paid_at=r.paid_at.isoformat() if r.paid_at else None,
        )
        for r in records
    ]


@router.post("/withdrawals", response_model=WithdrawalResponse)
async def create_withdrawal(
    request: WithdrawalRequestBody,
    user_id: str = Depends(get_current_user),
) -> WithdrawalResponse:
    """作者发起提现申请。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    if request.amount_cents <= 0:
        raise HTTPException(status_code=400, detail="提现金额必须大于 0")

    earnings = state.memory.get_author_earnings(user_id)
    if request.amount_cents > earnings["pending_cents"]:
        raise HTTPException(status_code=400, detail="可提现余额不足")

    withdrawal = WithdrawalRequestData(
        user_id=user_id,
        amount_cents=request.amount_cents,
        currency="usd",
        status="pending",
        payout_method=request.payout_method,
        payout_account=request.payout_account,
    )
    created = state.memory.create_withdrawal_request(withdrawal)

    # 预冻结：先扣减作者收益，若后续审核拒绝则退回
    state.memory.save_earning(
        EarningRecordData(
            user_id=user_id,
            record_type="withdrawal",
            amount=-request.amount_cents,
            description=f"提现申请冻结 {created.request_id}",
        )
    )

    return WithdrawalResponse(
        request_id=created.request_id,
        amount_cents=created.amount_cents,
        status=created.status,
        payout_method=created.payout_method,
        payout_account=created.payout_account,
        created_at=created.created_at.isoformat() if created.created_at else None,
    )


@router.get("/withdrawals", response_model=list[WithdrawalResponse])
async def list_withdrawals(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> list[WithdrawalResponse]:
    """获取当前登录作者的提现申请记录。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    records = state.memory.list_withdrawal_requests(
        user_id=user_id, status=status, limit=limit, offset=offset
    )
    return [
        WithdrawalResponse(
            request_id=r.request_id,
            amount_cents=r.amount_cents,
            status=r.status,
            payout_method=r.payout_method,
            payout_account=r.payout_account,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in records
    ]
