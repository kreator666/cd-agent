"""管理控制台路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from datetime import datetime

from comedy_agent.memory.models import BannedWordData, CryptoTipOrderData, EarningRecordData, IPStyleData, WithdrawalRequestData

router = APIRouter(tags=["admin"])

# 简单硬编码管理员列表（后续可迁移到数据库或配置）
ADMIN_USERS = {"admin"}


def require_admin(user_id: str = Depends(get_current_user)) -> str:
    """管理员权限校验。"""
    if user_id not in ADMIN_USERS:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user_id


class OverviewResponse(BaseModel):
    """平台概览响应。"""

    daily_active_users: int = Field(default=0, description="日活跃用户")
    total_generations: int = Field(default=0, description="总生成次数")
    ip_style_usage: int = Field(default=0, description="IP 风格总调用")
    salt_usage: int = Field(default=0, description="加点盐使用次数")
    pending_settlement: int = Field(default=0, description="待结算分成（分）")


class SkillReviewRequest(BaseModel):
    """Skill 审核请求。"""

    approved: bool = Field(description="是否通过")
    reason: str | None = Field(default=None, description="审核意见")


class BannedWordRequest(BaseModel):
    """敏感词添加请求。"""

    word: str = Field(description="敏感词")
    category: str | None = Field(default=None, description="分类")


@router.get("/admin/overview", response_model=OverviewResponse)
async def admin_overview(_admin: str = Depends(require_admin)) -> OverviewResponse:
    """平台概览数据。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    # TODO: 接入实际统计数据，当前返回占位值
    return OverviewResponse()


@router.get("/admin/skills/pending")
async def admin_pending_skills(_admin: str = Depends(require_admin)) -> dict[str, Any]:
    """待审核第三方 Skill 列表。"""
    # TODO: 接入 Skill 审核数据
    return {"skills": []}


@router.post("/admin/skills/{name}/review")
async def admin_review_skill(
    name: str,
    request: SkillReviewRequest,
    _admin: str = Depends(require_admin),
) -> dict[str, bool]:
    """审核 Skill。"""
    # TODO: 接入 Skill 审核逻辑
    return {"success": True}


@router.get("/admin/ip-styles")
async def admin_list_ip_styles(
    _admin: str = Depends(require_admin),
) -> list[IPStyleData]:
    """管理后台 IP 风格模型列表。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    return state.memory.list_ip_styles()


@router.put("/admin/ip-styles/{style_id}")
async def admin_update_ip_style(
    style_id: str,
    style: IPStyleData,
    _admin: str = Depends(require_admin),
) -> IPStyleData:
    """更新 IP 风格模型（状态、分成比例等）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    existing = state.memory.load_ip_style(style_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="IP 风格不存在")
    style.style_id = style_id
    return state.memory.save_ip_style(style)


@router.post("/admin/ip-roles", response_model=IPStyleData)
async def admin_create_ip_role(
    style: IPStyleData,
    _admin: str = Depends(require_admin),
) -> IPStyleData:
    """新增 IP 角色。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    return state.memory.save_ip_style(style)


@router.delete("/admin/ip-roles/{role_id}")
async def admin_delete_ip_role(
    role_id: str,
    _admin: str = Depends(require_admin),
) -> dict[str, bool]:
    """下架/删除 IP 角色。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    ok = state.memory.delete_ip_style(role_id)
    if not ok:
        raise HTTPException(status_code=404, detail="IP 角色不存在")
    return {"success": True}


@router.get("/admin/banned-words")
async def admin_list_banned_words(
    category: str | None = None,
    _admin: str = Depends(require_admin),
) -> list[BannedWordData]:
    """敏感词列表。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    return state.memory.list_banned_words(category=category)


@router.post("/admin/banned-words", response_model=BannedWordData)
async def admin_add_banned_word(
    request: BannedWordRequest,
    _admin: str = Depends(require_admin),
) -> BannedWordData:
    """添加敏感词。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    word = BannedWordData(word=request.word, category=request.category, added_by=_admin)
    return state.memory.save_banned_word(word)


@router.delete("/admin/banned-words/{word_id}")
async def admin_delete_banned_word(
    word_id: int,
    _admin: str = Depends(require_admin),
) -> dict[str, bool]:
    """删除敏感词。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    ok = state.memory.delete_banned_word(word_id)
    if not ok:
        raise HTTPException(status_code=404, detail="敏感词不存在")
    return {"success": True}


# ------------------------------------------------------------------ #
# 认证审核
# ------------------------------------------------------------------ #
class VerificationListResponse(BaseModel):
    """认证申请列表响应。"""

    applications: list[dict[str, Any]] = Field(description="申请列表")
    count: int = Field(description="总数")


class VerificationReviewRequest(BaseModel):
    """认证审核请求。"""

    review_note: str | None = Field(default=None, description="审核备注")


@router.get("/admin/verifications", response_model=VerificationListResponse)
async def admin_list_verifications(
    status: str | None = None,
    _admin: str = Depends(require_admin),
) -> VerificationListResponse:
    """获取认证申请列表（支持按状态过滤）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    apps = state.memory.list_verification_applications(status=status)
    return VerificationListResponse(applications=apps, count=len(apps))


@router.post("/admin/verifications/{app_id}/approve")
async def admin_approve_verification(
    app_id: int,
    request: VerificationReviewRequest,
    admin_id: str = Depends(require_admin),
) -> dict[str, Any]:
    """通过认证申请。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    result = state.memory.review_verification_application(
        app_id, approved=True, reviewer_id=admin_id, review_note=request.review_note
    )
    if result is None:
        raise HTTPException(status_code=404, detail="申请不存在")
    return result


@router.post("/admin/verifications/{app_id}/reject")
async def admin_reject_verification(
    app_id: int,
    request: VerificationReviewRequest,
    admin_id: str = Depends(require_admin),
) -> dict[str, Any]:
    """拒绝认证申请。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    result = state.memory.review_verification_application(
        app_id, approved=False, reviewer_id=admin_id, review_note=request.review_note
    )
    if result is None:
        raise HTTPException(status_code=404, detail="申请不存在")
    return result


class KnowledgeShareRequest(BaseModel):
    """知识库共享开关请求。"""

    shared: bool = Field(description="是否共享知识库给其他用户")


class KnowledgeShareResponse(BaseModel):
    """知识库共享状态响应。"""

    user_id: str = Field(description="用户ID")
    knowledge_shared: bool = Field(description="当前共享状态")


@router.get("/admin/users/{user_id}/knowledge", response_model=KnowledgeShareResponse)
async def admin_get_user_knowledge(
    user_id: str,
    _admin: str = Depends(require_admin),
) -> KnowledgeShareResponse:
    """查看大V用户的知识库共享状态。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    user = state.memory.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.is_verified:
        raise HTTPException(status_code=400, detail="该用户不是认证大V")
    return KnowledgeShareResponse(
        user_id=user_id,
        knowledge_shared=user.knowledge_shared,
    )


@router.post("/admin/users/{user_id}/knowledge-share", response_model=KnowledgeShareResponse)
async def admin_set_knowledge_share(
    user_id: str,
    request: KnowledgeShareRequest,
    _admin: str = Depends(require_admin),
) -> KnowledgeShareResponse:
    """设置大V用户的知识库共享开关。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    user = state.memory.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.is_verified:
        raise HTTPException(status_code=400, detail="该用户不是认证大V")
    updated = state.memory.update_user_profile(
        user_id, knowledge_shared=request.shared
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="更新失败")
    return KnowledgeShareResponse(
        user_id=user_id,
        knowledge_shared=updated.knowledge_shared,
    )


# ------------------------------------------------------------------ #
# 打赏提现审核
# ------------------------------------------------------------------ #
class WithdrawalAdminItem(BaseModel):
    """管理员视角提现申请项。"""

    request_id: str = Field(description="申请 ID")
    user_id: str = Field(description="申请人 ID")
    amount_cents: int = Field(description="提现金额（美分）")
    currency: str = Field(description="币种")
    status: str = Field(description="申请状态")
    payout_method: str | None = Field(default=None, description="收款方式")
    payout_account: str | None = Field(default=None, description="收款账号")
    created_at: str | None = Field(default=None, description="申请时间")
    processed_at: str | None = Field(default=None, description="处理时间")


class WithdrawalListResponse(BaseModel):
    """提现申请列表响应。"""

    requests: list[WithdrawalAdminItem] = Field(description="申请列表")
    count: int = Field(description="总数")


@router.get("/admin/withdrawals", response_model=WithdrawalListResponse)
async def admin_list_withdrawals(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: str = Depends(require_admin),
) -> WithdrawalListResponse:
    """获取提现申请列表（支持按状态过滤）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    records = state.memory.list_withdrawal_requests(status=status, limit=limit, offset=offset)
    items = [
        WithdrawalAdminItem(
            request_id=r.request_id,
            user_id=r.user_id,
            amount_cents=r.amount_cents,
            currency=r.currency,
            status=r.status,
            payout_method=r.payout_method,
            payout_account=r.payout_account,
            created_at=r.created_at.isoformat() if r.created_at else None,
            processed_at=r.processed_at.isoformat() if r.processed_at else None,
        )
        for r in records
    ]
    return WithdrawalListResponse(requests=items, count=len(items))


@router.post("/admin/withdrawals/{request_id}/approve", response_model=WithdrawalAdminItem)
async def admin_approve_withdrawal(
    request_id: str,
    _admin: str = Depends(require_admin),
) -> WithdrawalAdminItem:
    """通过提现申请。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    record = state.memory.get_withdrawal_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="提现申请不存在")
    if record.status != "pending":
        raise HTTPException(status_code=400, detail="仅待审核申请可通过")
    updated = state.memory.update_withdrawal_request_status(
        request_id, status="approved", processed_at=datetime.utcnow()
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="更新失败")
    return WithdrawalAdminItem(
        request_id=updated.request_id,
        user_id=updated.user_id,
        amount_cents=updated.amount_cents,
        currency=updated.currency,
        status=updated.status,
        payout_method=updated.payout_method,
        payout_account=updated.payout_account,
        created_at=updated.created_at.isoformat() if updated.created_at else None,
        processed_at=updated.processed_at.isoformat() if updated.processed_at else None,
    )


@router.post("/admin/withdrawals/{request_id}/reject", response_model=WithdrawalAdminItem)
async def admin_reject_withdrawal(
    request_id: str,
    _admin: str = Depends(require_admin),
) -> WithdrawalAdminItem:
    """拒绝提现申请，退回已冻结金额。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    record = state.memory.get_withdrawal_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="提现申请不存在")
    if record.status != "pending":
        raise HTTPException(status_code=400, detail="仅待审核申请可拒绝")
    updated = state.memory.update_withdrawal_request_status(
        request_id, status="rejected", processed_at=datetime.utcnow()
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="更新失败")
    # 拒绝后退回冻结金额
    state.memory.save_earning(
        EarningRecordData(
            user_id=updated.user_id,
            record_type="withdrawal_refund",
            amount=updated.amount_cents,
            description=f"提现申请拒绝退回 {updated.request_id}",
        )
    )
    return WithdrawalAdminItem(
        request_id=updated.request_id,
        user_id=updated.user_id,
        amount_cents=updated.amount_cents,
        currency=updated.currency,
        status=updated.status,
        payout_method=updated.payout_method,
        payout_account=updated.payout_account,
        created_at=updated.created_at.isoformat() if updated.created_at else None,
        processed_at=updated.processed_at.isoformat() if updated.processed_at else None,
    )


@router.post("/admin/withdrawals/{request_id}/paid", response_model=WithdrawalAdminItem)
async def admin_mark_withdrawal_paid(
    request_id: str,
    _admin: str = Depends(require_admin),
) -> WithdrawalAdminItem:
    """标记提现申请已打款。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    record = state.memory.get_withdrawal_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="提现申请不存在")
    if record.status != "approved":
        raise HTTPException(status_code=400, detail="仅已通过申请可标记为已打款")
    updated = state.memory.update_withdrawal_request_status(
        request_id, status="paid", processed_at=datetime.utcnow()
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="更新失败")
    return WithdrawalAdminItem(
        request_id=updated.request_id,
        user_id=updated.user_id,
        amount_cents=updated.amount_cents,
        currency=updated.currency,
        status=updated.status,
        payout_method=updated.payout_method,
        payout_account=updated.payout_account,
        created_at=updated.created_at.isoformat() if updated.created_at else None,
        processed_at=updated.processed_at.isoformat() if updated.processed_at else None,
    )



# ------------------------------------------------------------------ #
# 加密货币打赏订单审核
# ------------------------------------------------------------------ #
class CryptoTipOrderAdminItem(BaseModel):
    """管理员视角加密货币打赏订单项。"""

    order_id: str = Field(description="本地订单 ID")
    anyway_order_id: str | None = Field(default=None, description="Anyway 订单 ID")
    merchant_reference: str | None = Field(default=None, description="Merchant reference")
    result_id: str = Field(description="广场段子 result_id")
    payer_user_id: str = Field(description="打赏读者用户 ID")
    payer_wallet: str = Field(description="付款钱包地址")
    author_user_id: str = Field(description="被打赏作者用户 ID")
    author_wallet: str = Field(description="收款钱包地址")
    amount_cents: int = Field(description="金额（最小货币单位）")
    currency: str = Field(description="币种")
    status: str = Field(description="状态")
    tx_hash: str | None = Field(default=None, description="链上交易 hash")
    verified_at: str | None = Field(default=None, description="校验时间")
    created_at: str | None = Field(default=None, description="创建时间")


class CryptoTipOrderListResponse(BaseModel):
    """加密货币打赏订单列表响应。"""

    orders: list[CryptoTipOrderAdminItem] = Field(description="订单列表")
    count: int = Field(description="总数")


@router.get("/admin/crypto-tip-orders", response_model=CryptoTipOrderListResponse)
async def admin_list_crypto_tip_orders(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: str = Depends(require_admin),
) -> CryptoTipOrderListResponse:
    """获取加密货币打赏订单列表（支持按状态过滤）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    records = state.memory.list_crypto_tip_orders(status=status, limit=limit, offset=offset)
    items = [
        CryptoTipOrderAdminItem(
            order_id=r.order_id,
            anyway_order_id=r.anyway_order_id,
            merchant_reference=r.merchant_reference,
            result_id=r.result_id,
            payer_user_id=r.payer_user_id,
            payer_wallet=r.payer_wallet,
            author_user_id=r.author_user_id,
            author_wallet=r.author_wallet,
            amount_cents=r.amount_cents,
            currency=r.currency,
            status=r.status,
            tx_hash=r.tx_hash,
            verified_at=r.verified_at.isoformat() if r.verified_at else None,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in records
    ]
    return CryptoTipOrderListResponse(orders=items, count=len(items))


@router.post("/admin/crypto-tip-orders/{order_id}/verify")
async def admin_verify_crypto_tip_order(
    order_id: str,
    tx_hash: str | None = None,
    _admin: str = Depends(require_admin),
) -> dict[str, Any]:
    """手动触发链上校验并入账。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    from comedy_agent.services.crypto_chain import verify_tip_payment

    record = state.memory.get_crypto_tip_order(order_id)
    if record is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    tx = tx_hash or record.tx_hash
    if not tx:
        raise HTTPException(status_code=400, detail="缺少链上交易 hash")

    verification = verify_tip_payment(
        tx_hash=tx,
        expected_author_wallet=record.author_wallet,
        expected_payer_wallet=record.payer_wallet,
        expected_amount=record.amount_cents,
        currency=record.currency,
    )
    if not verification["success"]:
        raise HTTPException(status_code=400, detail=verification.get("error") or "链上校验失败")

    updated = state.memory.update_crypto_tip_order(
        order_id=record.order_id,
        tx_hash=tx,
        status="paid",
        verified_at=datetime.utcnow(),
        paid_at=datetime.utcnow(),
        metadata_json={"chain_verification": verification},
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="入账更新失败")
    return {"order_id": order_id, "status": "paid", "verification": verification}
