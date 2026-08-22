"""加密货币打赏路由。

读者使用个人钱包付款，作者使用个人钱包收款，平台通过 Anyway 订单 + Base 链上交易校验入账。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.core.config import settings
from comedy_agent.memory.models import CryptoTipOrderData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tips/crypto", tags=["crypto-tips"])


class CreateCryptoTipRequest(BaseModel):
    """创建加密货币打赏请求。"""

    result_id: str = Field(description="广场段子 result_id")
    amount_cents: int = Field(ge=1, description="金额（最小货币单位，如 USDC 的 6 位小数单位）")
    currency: str = Field(default="USDC", description="币种：USDC / ETH")


class CreateCryptoTipResponse(BaseModel):
    """创建加密货币打赏响应。"""

    order_id: str = Field(description="本地订单 ID")
    payment_url: str = Field(description="Anyway 付款链接")
    payer_wallet: str = Field(description="读者付款钱包地址")
    author_wallet: str = Field(description="作者收款钱包地址")
    amount_cents: int = Field(description="金额（最小货币单位）")
    currency: str = Field(description="币种")


class ConfirmCryptoTipRequest(BaseModel):
    """手动确认加密货币打赏请求。"""

    order_id: str = Field(description="本地订单 ID")
    tx_hash: str = Field(description="Base 链上交易 hash")


class CryptoTipOrderResponse(BaseModel):
    """加密货币打赏订单响应。"""

    order_id: str
    result_id: str
    payer_wallet: str
    author_wallet: str
    amount_cents: int
    currency: str
    status: str
    tx_hash: str | None
    verified_at: str | None
    created_at: str | None
    paid_at: str | None


class CryptoStatsResponse(BaseModel):
    """加密货币打赏统计响应。"""

    total_tipped_cents: int
    total_received_cents: int
    bound_wallet: str | None
    wallet_chain: str
    currency: str


def _to_checksum(address: str) -> str:
    from eth_utils import to_checksum_address
    return to_checksum_address(address)


@router.post("/intent", response_model=CreateCryptoTipResponse)
async def create_crypto_tip_intent(
    request: CreateCryptoTipRequest,
    user_id: str = Depends(get_current_user),
) -> CreateCryptoTipResponse:
    """创建加密货币打赏意图，返回 Anyway 付款链接。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    if not settings.anyway_payment_link_url:
        raise HTTPException(status_code=503, detail="Anyway payment link 未配置")

    # 校验广场段子与作者
    result = state.memory.get_eval_result(request.result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="段子不存在或未发布")
    author_id = getattr(result, "user_id", None)
    if not author_id:
        raise HTTPException(status_code=404, detail="无法确定作者")
    if author_id == user_id:
        raise HTTPException(status_code=400, detail="不能给自己打赏")

    # 校验读者钱包
    payer = state.memory.get_user(user_id)
    if payer is None or not payer.wallet_address:
        raise HTTPException(status_code=400, detail="请先绑定加密货币钱包")

    author = state.memory.get_user(author_id)
    if author is None or not author.wallet_address:
        raise HTTPException(status_code=400, detail="作者未绑定加密货币钱包")

    order_id = "cto_" + uuid.uuid4().hex[:16]
    merchant_reference = order_id

    order = CryptoTipOrderData(
        order_id=order_id,
        merchant_reference=merchant_reference,
        result_id=request.result_id,
        payer_user_id=user_id,
        payer_wallet=_to_checksum(payer.wallet_address),
        author_user_id=author_id,
        author_wallet=_to_checksum(author.wallet_address),
        amount_cents=request.amount_cents,
        currency=request.currency.upper(),
        status="pending",
    )
    state.memory.create_crypto_tip_order(order)

    payment_url = (
        f"{settings.anyway_payment_link_url}?"
        f"merchant_reference={merchant_reference}&"
        f"payer_wallet={order.payer_wallet}&"
        f"author_wallet={order.author_wallet}&"
        f"result_id={request.result_id}&"
        f"payer_user_id={user_id}"
    )

    return CreateCryptoTipResponse(
        order_id=order_id,
        payment_url=payment_url,
        payer_wallet=order.payer_wallet,
        author_wallet=order.author_wallet,
        amount_cents=request.amount_cents,
        currency=order.currency,
    )


@router.post("/confirm", response_model=CryptoTipOrderResponse)
async def confirm_crypto_tip(
    request: ConfirmCryptoTipRequest,
    user_id: str = Depends(get_current_user),
) -> CryptoTipOrderResponse:
    """手动提交链上交易 hash，完成链上校验并入账。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    order = state.memory.get_crypto_tip_order(request.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.payer_user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作该订单")
    if order.status == "paid":
        raise HTTPException(status_code=400, detail="订单已入账")

    from comedy_agent.services.crypto_chain import verify_tip_payment

    verification = verify_tip_payment(
        tx_hash=request.tx_hash,
        expected_author_wallet=order.author_wallet,
        expected_payer_wallet=order.payer_wallet,
        expected_amount=order.amount_cents,
        currency=order.currency,
    )
    if not verification["success"]:
        raise HTTPException(status_code=400, detail=verification.get("error") or "链上校验失败")

    updated = state.memory.update_crypto_tip_order(
        order_id=order.order_id,
        tx_hash=request.tx_hash,
        status="paid",
        verified_at=datetime.now(timezone.utc),
        paid_at=datetime.now(timezone.utc),
        metadata_json={
            "chain_verification": verification,
        },
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="入账更新失败")

    return _order_to_response(updated)


@router.get("/orders", response_model=list[CryptoTipOrderResponse])
async def list_crypto_tip_orders(
    role: str | None = None,
    status: str | None = None,
    user_id: str = Depends(get_current_user),
) -> list[CryptoTipOrderResponse]:
    """获取当前用户的加密货币打赏订单列表。

    role: payer / author，不传则同时返回我打赏和我收到的订单。
    """
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    if role == "payer":
        records = state.memory.list_crypto_tip_orders(payer_user_id=user_id, status=status)
    elif role == "author":
        records = state.memory.list_crypto_tip_orders(author_user_id=user_id, status=status)
    else:
        payer_records = state.memory.list_crypto_tip_orders(payer_user_id=user_id, status=status)
        author_records = state.memory.list_crypto_tip_orders(author_user_id=user_id, status=status)
        seen = set()
        records = []
        for r in payer_records + author_records:
            if r.order_id in seen:
                continue
            seen.add(r.order_id)
            records.append(r)
        records.sort(key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    return [_order_to_response(r) for r in records]


@router.get("/stats", response_model=CryptoStatsResponse)
async def get_crypto_tip_stats(
    user_id: str = Depends(get_current_user),
) -> CryptoStatsResponse:
    """获取当前用户的加密货币打赏统计。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    stats = state.memory.get_crypto_tip_stats(user_id)
    return CryptoStatsResponse(
        total_tipped_cents=stats["total_tipped_cents"],
        total_received_cents=stats["total_received_cents"],
        bound_wallet=stats["bound_wallet"],
        wallet_chain=stats["wallet_chain"],
        currency=stats["currency"],
    )


def _order_to_response(order: CryptoTipOrderData) -> CryptoTipOrderResponse:
    return CryptoTipOrderResponse(
        order_id=order.order_id,
        result_id=order.result_id,
        payer_wallet=order.payer_wallet,
        author_wallet=order.author_wallet,
        amount_cents=order.amount_cents,
        currency=order.currency,
        status=order.status,
        tx_hash=order.tx_hash,
        verified_at=order.verified_at.isoformat() if order.verified_at else None,
        created_at=order.created_at.isoformat() if order.created_at else None,
        paid_at=order.paid_at.isoformat() if order.paid_at else None,
    )
