"""钱包与 Token 账户路由。"""

from __future__ import annotations

import io
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import qrcode
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.core.config import settings
from comedy_agent.services.crypto_wallet import (
    build_wallet_sign_message,
    get_wallet_sign_content,
    validate_ethereum_address,
    verify_wallet_signature,
)

router = APIRouter(tags=["wallet"])


class UserDetailResponse(BaseModel):
    """用户详情响应（含粉丝/关注数）。"""

    user_id: str = Field(description="用户 ID")
    nickname: str | None = Field(default=None, description="昵称")
    bio: str | None = Field(default=None, description="个人简介")
    tags: list[str] | None = Field(default=None, description="兴趣标签")
    avatar_url: str | None = Field(default=None, description="头像 URL")
    is_verified: bool = Field(default=False, description="是否认证大V")
    follower_count: int = Field(default=0, description="粉丝数")
    following_count: int = Field(default=0, description="关注数")
    created_at: str | None = Field(default=None, description="创建时间")


class UpdateProfileRequest(BaseModel):
    """更新个人信息请求。"""

    nickname: str | None = Field(default=None, description="昵称")
    bio: str | None = Field(default=None, description="个人简介")
    tags: list[str] | None = Field(default=None, description="兴趣标签")
    avatar_url: str | None = Field(default=None, description="头像 URL")


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


class StatsResponse(BaseModel):
    """用户统计响应。"""

    generations: int = Field(default=0, description="Comedy Agent 生成次数")
    actor_usage: int = Field(default=0, description="虚拟演员调用次数")
    salt_usage: int = Field(default=0, description="加点盐调用次数")
    earnings: int = Field(default=0, description="累计收益（分）")


@router.get("/me/stats", response_model=StatsResponse)
async def get_stats(user_id: str = Depends(get_current_user)) -> StatsResponse:
    """获取当前用户使用统计。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    stats = state.memory.get_user_stats(user_id)
    return StatsResponse(
        generations=stats.get("generations", 0),
        actor_usage=stats.get("actor_usage", 0),
        salt_usage=stats.get("salt_usage", 0),
        earnings=stats.get("earnings", 0),
    )


class ConsumptionRecordResponse(BaseModel):
    """单条消费记录响应。"""

    consumption_id: str = Field(description="记录 ID")
    session_id: str | None = Field(default=None, description="会话 ID")
    endpoint: str | None = Field(default=None, description="调用入口")
    model: str | None = Field(default=None, description="模型名")
    prompt_tokens: int = Field(default=0, description="输入 Token 数")
    completion_tokens: int = Field(default=0, description="输出 Token 数")
    total_tokens: int = Field(default=0, description="总 Token 数")
    cost: int = Field(default=0, description="扣除 Token 数")
    description: str | None = Field(default=None, description="描述")
    created_at: str | None = Field(default=None, description="创建时间")


class ConsumptionListResponse(BaseModel):
    """消费记录列表响应。"""

    items: list[ConsumptionRecordResponse] = Field(description="消费记录列表")
    total: int = Field(default=0, description="总记录数")


@router.get("/me/consumptions", response_model=ConsumptionListResponse)
async def list_consumptions(
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
) -> ConsumptionListResponse:
    """获取当前用户的模型调用消费明细。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    records = state.memory.list_consumption_records(user_id, limit=limit, offset=offset)
    return ConsumptionListResponse(
        items=[
            ConsumptionRecordResponse(
                consumption_id=r.consumption_id or "",
                session_id=r.session_id,
                endpoint=r.endpoint,
                model=r.model,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                total_tokens=r.total_tokens,
                cost=r.cost,
                description=r.description,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in records
        ],
        total=len(records),
    )


# ------------------------------------------------------------------ #
# 模型配置
# ------------------------------------------------------------------ #
class ModelConfigResponse(BaseModel):
    """用户模型配置响应。"""

    speed_model: str | None = Field(default=None, description="极速版使用的模型")
    pro_model: str | None = Field(default=None, description="专业版使用的模型")


class ModelConfigRequest(BaseModel):
    """用户模型配置请求。"""

    speed_model: str | None = Field(default=None, description="极速版使用的模型")
    pro_model: str | None = Field(default=None, description="专业版使用的模型")


@router.get("/me/model-config", response_model=ModelConfigResponse)
async def get_model_config(user_id: str = Depends(get_current_user)) -> ModelConfigResponse:
    """获取当前用户的模型配置（极速版/专业版）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    prefs = state.memory.list_preferences(user_id)
    config: dict[str, Any] = {}
    for p in prefs:
        if p.key == "model_config" and p.value:
            config = p.value
    return ModelConfigResponse(
        speed_model=config.get("speed_model"),
        pro_model=config.get("pro_model"),
    )


@router.post("/me/model-config", response_model=ModelConfigResponse)
async def save_model_config(
    request: ModelConfigRequest, user_id: str = Depends(get_current_user)
) -> ModelConfigResponse:
    """保存当前用户的模型配置（极速版/专业版）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    state.memory.save_preference(
        user_id=user_id,
        key="model_config",
        value={
            "speed_model": request.speed_model,
            "pro_model": request.pro_model,
        },
    )
    return ModelConfigResponse(
        speed_model=request.speed_model,
        pro_model=request.pro_model,
    )


class AvatarResponse(BaseModel):
    """头像上传响应。"""

    avatar_url: str = Field(description="头像访问 URL")


@router.post("/me/avatar", response_model=AvatarResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
) -> AvatarResponse:
    """上传头像图片文件，保存到 static/avatars/ 目录。"""
    frontend_dir = Path(__file__).resolve().parent.parent.parent.parent.parent / "frontend"
    avatars_dir = frontend_dir / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    # 安全检查：只允许图片
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只允许上传图片文件")

    # 生成安全文件名：user_id + 扩展名
    suffix = Path(file.filename or "avatar.jpg").suffix
    if suffix.lower() not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        suffix = ".jpg"
    save_name = f"{user_id}{suffix}"
    save_path = avatars_dir / save_name

    content = await file.read()
    save_path.write_bytes(content)

    avatar_url = f"/static/avatars/{save_name}"
    # 同时更新用户资料中的头像 URL
    if state.memory is not None:
        state.memory.update_user_profile(user_id, avatar_url=avatar_url)

    return AvatarResponse(avatar_url=avatar_url)


class TippingConfigResponse(BaseModel):
    """微信打赏配置响应。"""

    qr_url: str | None = Field(default=None, description="微信收款二维码访问 URL")
    tipping_copy: str | None = Field(default=None, description="打赏文案")
    usdt_address: str | None = Field(default=None, description="USDT 以太坊收款地址")


_MAX_QR_SIZE = 2 * 1024 * 1024  # 2 MB


def _validate_usdt_address(address: str) -> bool:
    """校验以太坊地址格式：0x 前缀 + 40 位十六进制。"""
    return bool(re.fullmatch(r"0x[a-fA-F0-9]{40}", address))


@router.get("/me/tipping-config", response_model=TippingConfigResponse)
async def get_tipping_config(
    user_id: str = Depends(get_current_user),
) -> TippingConfigResponse:
    """获取当前用户的微信打赏配置。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    user = state.memory.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return TippingConfigResponse(
        qr_url=user.wechat_pay_qr_url,
        tipping_copy=user.tipping_copy,
        usdt_address=user.usdt_address,
    )


@router.post("/me/tipping-config", response_model=TippingConfigResponse)
async def update_tipping_config(
    tipping_copy: str = Form("", description="打赏文案"),
    usdt_address: str = Form("", description="USDT 以太坊收款地址，以 0x 开头共 42 字符"),
    file: UploadFile | None = File(None, description="微信收款二维码图片（可选，不传则保留已有）"),
    user_id: str = Depends(get_current_user),
) -> TippingConfigResponse:
    """更新当前用户的打赏配置。

    - 上传新的二维码图片会覆盖旧文件并更新 URL；
    - 不传图片时只更新文案，保留已有二维码；
    - 传空文案可清空文案，但二维码不会被删除；
    - usdt_address 传空字符串可清空地址。
    """
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    if usdt_address and not _validate_usdt_address(usdt_address):
        raise HTTPException(status_code=400, detail="USDT 地址格式不正确，应为 0x 开头的 42 位以太坊地址")

    qr_url: str | None = None
    if file is not None:
        content_type = file.content_type or ""
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="只允许上传图片文件")
        suffix = Path(file.filename or "qr.png").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
            suffix = ".png"

        content = await file.read()
        if len(content) > _MAX_QR_SIZE:
            raise HTTPException(status_code=400, detail="二维码图片大小不能超过 2MB")

        frontend_dir = Path(__file__).resolve().parent.parent.parent.parent.parent / "frontend"
        qr_dir = frontend_dir / "qr_codes"
        qr_dir.mkdir(parents=True, exist_ok=True)
        save_name = f"{user_id}{suffix}"
        save_path = qr_dir / save_name
        save_path.write_bytes(content)
        qr_url = f"/static/qr_codes/{save_name}"

    user = state.memory.update_user_profile(
        user_id=user_id,
        wechat_pay_qr_url=qr_url,
        tipping_copy=tipping_copy if tipping_copy is not None else "",
        usdt_address=usdt_address if usdt_address is not None else "",
    )
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return TippingConfigResponse(
        qr_url=user.wechat_pay_qr_url,
        tipping_copy=user.tipping_copy,
        usdt_address=user.usdt_address,
    )


@router.get("/tipping/usdt-qr/{user_id}")
async def get_usdt_qr(user_id: str) -> Response:
    """根据用户 ID 生成 USDT 收款地址二维码图片。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    user = state.memory.get_user(user_id)
    if user is None or not user.usdt_address:
        raise HTTPException(status_code=404, detail="用户未设置 USDT 收款地址")

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(user.usdt_address)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")


# --------------------------------------------------------------------------- #
# 加密货币钱包绑定
# --------------------------------------------------------------------------- #
class WalletAddressResponse(BaseModel):
    """钱包地址绑定状态响应。"""

    wallet_address: str | None = Field(default=None, description="已绑定钱包地址")
    wallet_chain: str = Field(default="base", description="链标识")
    wallet_signed_at: str | None = Field(default=None, description="绑定时间")


class WalletSignMessageResponse(BaseModel):
    """钱包签名消息响应。"""

    address: str = Field(description="待绑定地址")
    content: str = Field(description="展示给用户的签名提示内容")
    nonce: str = Field(description="签名随机串")
    typed_data: dict[str, Any] = Field(description="完整 EIP-712 消息，可直接交给钱包 signTypedData")


class BindWalletRequest(BaseModel):
    """绑定钱包地址请求。"""

    address: str = Field(description="钱包地址")
    signature: str = Field(description="EIP-712 签名 hex")
    nonce: str = Field(default="", description="签名随机串")
    chain: str = Field(default="base", description="链标识：base / ethereum")


@router.get("/me/wallet-address", response_model=WalletAddressResponse)
async def get_wallet_address(
    user_id: str = Depends(get_current_user),
) -> WalletAddressResponse:
    """获取当前用户绑定的加密货币钱包地址。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    user = state.memory.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return WalletAddressResponse(
        wallet_address=user.wallet_address,
        wallet_chain=user.wallet_chain,
        wallet_signed_at=user.wallet_signed_at.isoformat() if user.wallet_signed_at else None,
    )


@router.get("/me/wallet-address/sign-message", response_model=WalletSignMessageResponse)
async def get_wallet_sign_message_endpoint(
    address: str,
    chain: str = "base",
    user_id: str = Depends(get_current_user),
) -> WalletSignMessageResponse:
    """为指定地址生成 EIP-712 签名消息。

    前端调用钱包 signTypedData 后，将 address、signature、nonce 提交到 POST /me/wallet-address。
    """
    if not validate_ethereum_address(address):
        raise HTTPException(status_code=400, detail="钱包地址格式不正确")
    if chain not in {"base", "ethereum"}:
        raise HTTPException(status_code=400, detail="不支持的链")
    content = get_wallet_sign_content(address)
    nonce = uuid.uuid4().hex[:16]
    typed_data = build_wallet_sign_message(address, content, nonce, chain=chain)
    return WalletSignMessageResponse(
        address=address,
        content=content,
        nonce=nonce,
        typed_data=typed_data,
    )


@router.post("/me/wallet-address", response_model=WalletAddressResponse)
async def bind_wallet_address(
    request: BindWalletRequest,
    user_id: str = Depends(get_current_user),
) -> WalletAddressResponse:
    """绑定加密货币钱包地址，需提交 EIP-712 签名进行所有权校验。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    if not validate_ethereum_address(request.address):
        raise HTTPException(status_code=400, detail="钱包地址格式不正确")

    if request.chain not in {"base", "ethereum"}:
        raise HTTPException(status_code=400, detail="不支持的链")

    content = get_wallet_sign_content(request.address)
    if not verify_wallet_signature(
        request.address, content, request.nonce, request.signature, chain=request.chain
    ):
        raise HTTPException(status_code=400, detail="签名验证失败，请使用对应地址签名")

    user = state.memory.update_user_profile(
        user_id,
        wallet_address=request.address.lower(),
        wallet_signature=request.signature,
        wallet_signed_at=datetime.now(timezone.utc),
        wallet_chain=request.chain,
    )
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return WalletAddressResponse(
        wallet_address=user.wallet_address,
        wallet_chain=user.wallet_chain,
        wallet_signed_at=user.wallet_signed_at.isoformat() if user.wallet_signed_at else None,
    )


@router.get("/me", response_model=UserDetailResponse)
async def me(user_id: str = Depends(get_current_user)) -> UserDetailResponse:
    """获取当前登录用户信息（含粉丝数、关注数）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    user = state.memory.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserDetailResponse(
        user_id=user.user_id,
        nickname=user.nickname,
        bio=user.bio,
        tags=user.tags,
        avatar_url=user.avatar_url,
        is_verified=user.is_verified,
        follower_count=state.memory.count_followers(user_id),
        following_count=state.memory.count_following(user_id),
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.put("/me", response_model=UserDetailResponse)
async def update_me(
    request: UpdateProfileRequest,
    user_id: str = Depends(get_current_user),
) -> UserDetailResponse:
    """更新当前登录用户个人信息。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    user = state.memory.update_user_profile(
        user_id=user_id,
        nickname=request.nickname,
        bio=request.bio,
        tags=request.tags,
        avatar_url=request.avatar_url,
    )
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserDetailResponse(
        user_id=user.user_id,
        nickname=user.nickname,
        bio=user.bio,
        tags=user.tags,
        avatar_url=user.avatar_url,
        is_verified=user.is_verified,
        follower_count=state.memory.count_followers(user_id),
        following_count=state.memory.count_following(user_id),
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


class VerifyApplyRequest(BaseModel):
    """认证申请请求。"""

    reason: str | None = Field(default=None, description="申请理由")


class VerificationResponse(BaseModel):
    """认证申请/状态响应。"""

    id: int | None = Field(default=None, description="申请 ID")
    user_id: str | None = Field(default=None, description="用户 ID")
    status: str = Field(default="pending", description="pending / approved / rejected")
    reason: str | None = Field(default=None, description="申请理由")
    review_note: str | None = Field(default=None, description="审核备注")
    applied_at: str | None = Field(default=None, description="申请时间")
    reviewed_at: str | None = Field(default=None, description="审核时间")
    reviewer_id: str | None = Field(default=None, description="审核人 ID")


@router.post("/me/verify-apply", response_model=VerificationResponse)
async def apply_verification(
    request: VerifyApplyRequest,
    user_id: str = Depends(get_current_user),
) -> VerificationResponse:
    """提交认证（大V）申请。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    result = state.memory.apply_verification(user_id, reason=request.reason)
    return VerificationResponse(**result)


@router.get("/me/verification", response_model=VerificationResponse)
async def get_my_verification(user_id: str = Depends(get_current_user)) -> VerificationResponse:
    """查询当前用户的认证申请状态。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    result = state.memory.get_user_verification(user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="暂无认证申请记录")
    return VerificationResponse(**result)
