"""物品/服务交换平台路由 —— swap。

提供闲置物品/技能互换的订单发布、意向提交、成交与精选能力。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from comedy_agent.api.routers.admin import require_admin
from comedy_agent.api.state import state
from comedy_agent.api.static_mirror import mirror_upload
from comedy_agent.auth.dependencies import get_current_user, oauth2_scheme
from comedy_agent.auth.security import decode_access_token
from comedy_agent.memory.models import SwapOfferData, SwapOrderData

router = APIRouter(prefix="/swap", tags=["swap"])

MAX_SWAP_IMAGES = 3
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class SwapOrderCreateRequest(BaseModel):
    """发布交换订单请求。"""

    title: str = Field(max_length=128, description="标题")
    offer_desc: str = Field(description="我提供什么")
    want_desc: str = Field(description="想换什么")
    images: list[str] = Field(default_factory=list, description="配图 URL 列表，最多 3 张")


class SwapOfferCreateRequest(BaseModel):
    """提交交换意向请求。"""

    item_desc: str = Field(description="我拿什么交换")
    contact: str = Field(max_length=256, description="联系方式")
    images: list[str] = Field(default_factory=list, description="配图 URL 列表，最多 3 张")


class SwapFeatureRequest(BaseModel):
    """订单精选设置请求。"""

    featured: bool = Field(description="是否精选")


class SwapOrderResponse(BaseModel):
    """交换订单响应。"""

    order_id: str | None = Field(default=None, description="订单 ID")
    maker_id: str = Field(description="发布者用户 ID")
    title: str = Field(description="标题")
    offer_desc: str = Field(description="我提供什么")
    want_desc: str = Field(description="想换什么")
    images: list[str] = Field(default_factory=list, description="配图 URL 列表")
    status: str = Field(description="状态：open / deal / closed")
    featured: bool = Field(default=False, description="是否精选")
    featured_at: str | None = Field(default=None, description="精选时间")
    deal_offer_id: str | None = Field(default=None, description="成交的交换意向 ID")
    created_at: str | None = Field(default=None, description="创建时间")
    updated_at: str | None = Field(default=None, description="更新时间")
    offer_count: int = Field(default=0, description="交换意向数")


class SwapOrderDetailResponse(SwapOrderResponse):
    """交换订单详情响应（可能附带意向列表）。"""

    offers: list["SwapOfferResponse"] | None = Field(
        default=None, description="意向列表（仅发布者或成交方可见）"
    )
    my_offer: "SwapOfferResponse | None" = Field(
        default=None, description="当前登录用户自己提交的意向（含联系方式，用于表单回填）"
    )


class SwapOfferResponse(BaseModel):
    """交换意向响应。contact 按权限脱敏：无权限时不下发该字段。"""

    offer_id: str | None = Field(default=None, description="意向 ID")
    order_id: str = Field(description="所属订单 ID")
    taker_id: str = Field(description="提交者用户 ID")
    item_desc: str = Field(description="我拿什么交换")
    images: list[str] = Field(default_factory=list, description="配图 URL 列表")
    contact: str | None = Field(default=None, description="联系方式（脱敏）")
    status: str = Field(description="状态：pending / accepted / rejected")
    created_at: str | None = Field(default=None, description="创建时间")
    updated_at: str | None = Field(default=None, description="更新时间")


class SwapMyOrderResponse(SwapOrderResponse):
    """我发布的交换订单响应。"""

    pending_count: int = Field(default=0, description="待处理意向数")


class SwapMyOfferResponse(SwapOfferResponse):
    """我提交的交换意向响应（附带所属订单摘要）。"""

    order_title: str | None = Field(default=None, description="所属订单标题")
    order_status: str | None = Field(default=None, description="所属订单状态")


class SwapOrderListResponse(BaseModel):
    """交换订单列表响应。"""

    orders: list[SwapOrderResponse] = Field(description="订单列表")
    total: int = Field(description="符合条件的订单总数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页数量")


def _get_optional_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> str | None:
    """可选登录：已登录返回 user_id，未登录或凭证无效返回 None。"""
    if not token:
        return None
    try:
        return decode_access_token(token)
    except Exception:
        return None


def _contact_visible(offer: SwapOfferData, order: SwapOrderData, viewer: str | None) -> bool:
    """联系方式脱敏：发布者可见明文；成交后成交双方可见明文；其余不下发。"""
    if viewer is not None and viewer == order.maker_id:
        return True
    if order.status == "deal" and viewer is not None and viewer == offer.taker_id:
        return True
    return False


def _offer_response(
    offer: SwapOfferData, order: SwapOrderData, viewer: str | None
) -> SwapOfferResponse:
    """构建意向响应，按请求者权限脱敏 contact。"""
    data = offer.model_dump()
    data["contact"] = offer.contact if _contact_visible(offer, order, viewer) else None
    return SwapOfferResponse(**data)


def _order_response(order: SwapOrderData) -> SwapOrderResponse:
    """构建订单响应，附带 offer_count。"""
    data = order.model_dump()
    data["offer_count"] = state.memory.count_swap_offers(order.order_id)
    return SwapOrderResponse(**data)


@router.post("/orders", response_model=SwapOrderResponse)
async def create_swap_order(
    request: SwapOrderCreateRequest,
    user_id: str = Depends(get_current_user),
) -> SwapOrderResponse:
    """发布交换订单。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    if len(request.images) > MAX_SWAP_IMAGES:
        raise HTTPException(status_code=400, detail="配图最多 3 张")
    order = SwapOrderData(
        maker_id=user_id,
        title=request.title,
        offer_desc=request.offer_desc,
        want_desc=request.want_desc,
        images=request.images,
    )
    saved = state.memory.save_swap_order(order)
    return _order_response(saved)


@router.get("/orders", response_model=SwapOrderListResponse)
async def list_swap_orders(
    featured: bool = False,
    status: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 12,
) -> SwapOrderListResponse:
    """公开列出交换订单，支持精选/状态/关键词过滤与分页。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    page = max(page, 1)
    page_size = min(page_size, 50)
    offset = (page - 1) * page_size
    featured_filter = featured if featured else None
    orders = state.memory.list_swap_orders(
        status=status,
        featured=featured_filter,
        keyword=keyword,
        limit=page_size,
        offset=offset,
    )
    total = state.memory.count_swap_orders(
        status=status, featured=featured_filter, keyword=keyword
    )
    return SwapOrderListResponse(
        orders=[_order_response(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/orders/{order_id}",
    response_model=SwapOrderDetailResponse,
    response_model_exclude_none=True,
)
async def get_swap_order_detail(
    order_id: str,
    viewer: str | None = Depends(_get_optional_user),
) -> SwapOrderDetailResponse:
    """交换订单详情。发布者可见全部意向；成交后成交双方可见成交意向。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    order = state.memory.get_swap_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    payload = order.model_dump()
    payload["offer_count"] = state.memory.count_swap_offers(order_id)

    offers_data: list[SwapOfferData] | None = None
    if viewer is not None and viewer == order.maker_id:
        offers_data = state.memory.list_swap_offers(order_id=order_id)
    elif order.status == "deal" and order.deal_offer_id and viewer is not None:
        deal_offer = state.memory.get_swap_offer(order.deal_offer_id)
        if deal_offer is not None and deal_offer.taker_id == viewer:
            offers_data = [deal_offer]

    if offers_data is not None:
        payload["offers"] = [
            _offer_response(offer, order, viewer).model_dump() for offer in offers_data
        ]
    elif viewer is not None and viewer != order.maker_id:
        # 非发布者：附带自己已提交的意向（联系方式为本人数据，直接明文回填表单）
        mine = state.memory.list_swap_offers(order_id=order_id, taker_id=viewer)
        if mine:
            my = mine[0].model_dump()
            payload["my_offer"] = SwapOfferResponse(**my).model_dump()
    return SwapOrderDetailResponse(**payload)


@router.get("/my/orders", response_model=list[SwapMyOrderResponse])
async def my_swap_orders(
    user_id: str = Depends(get_current_user),
) -> list[SwapMyOrderResponse]:
    """我发布的交换订单列表，附带意向数与待处理数。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    orders = state.memory.list_swap_orders(maker_id=user_id, limit=1000, offset=0)
    result = []
    for order in orders:
        offers = state.memory.list_swap_offers(order_id=order.order_id)
        data = order.model_dump()
        data["offer_count"] = len(offers)
        data["pending_count"] = sum(1 for f in offers if f.status == "pending")
        result.append(SwapMyOrderResponse(**data))
    return result


@router.get("/my/offers", response_model=list[SwapMyOfferResponse], response_model_exclude_none=True)
async def my_swap_offers(
    user_id: str = Depends(get_current_user),
) -> list[SwapMyOfferResponse]:
    """我提交的交换意向列表（按更新时间倒序），附带所属订单标题与状态。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    offers = state.memory.list_swap_offers(taker_id=user_id)
    result = []
    for offer in offers:
        order = state.memory.get_swap_order(offer.order_id)
        data = offer.model_dump()
        data["order_title"] = order.title if order else None
        data["order_status"] = order.status if order else None
        data["contact"] = (
            offer.contact if (order and _contact_visible(offer, order, user_id)) else None
        )
        result.append(SwapMyOfferResponse(**data))
    return result


@router.post(
    "/orders/{order_id}/offers",
    response_model=SwapOfferResponse,
    response_model_exclude_none=True,
)
async def create_swap_offer(
    order_id: str,
    request: SwapOfferCreateRequest,
    user_id: str = Depends(get_current_user),
) -> SwapOfferResponse:
    """对交换订单提交意向；同一订单重复提交则更新原意向内容。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    if len(request.images) > MAX_SWAP_IMAGES:
        raise HTTPException(status_code=400, detail="配图最多 3 张")

    order = state.memory.get_swap_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != "open":
        raise HTTPException(status_code=400, detail="订单当前不可交换")
    if order.maker_id == user_id:
        raise HTTPException(status_code=400, detail="不能对自己发布的订单提交交换")

    # 先查再更新：同一用户对同一订单仅保留一条意向（唯一约束 uq_swap_offer_order_taker）
    existing = state.memory.list_swap_offers(order_id=order_id, taker_id=user_id)
    if existing:
        offer = existing[0]
        offer.item_desc = request.item_desc
        offer.contact = request.contact
        offer.images = request.images
        saved = state.memory.save_swap_offer(offer)
    else:
        saved = state.memory.save_swap_offer(
            SwapOfferData(
                order_id=order_id,
                taker_id=user_id,
                item_desc=request.item_desc,
                contact=request.contact,
                images=request.images,
            )
        )
    return _offer_response(saved, order, user_id)


@router.post("/offers/{offer_id}/accept", response_model=SwapOrderResponse)
async def accept_swap_offer(
    offer_id: str,
    user_id: str = Depends(get_current_user),
) -> SwapOrderResponse:
    """订单发布者确认成交：该意向 accepted，同单其他 pending 意向 rejected。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    offer = state.memory.get_swap_offer(offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="交换意向不存在")
    order = state.memory.get_swap_order(offer.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.maker_id != user_id:
        raise HTTPException(status_code=403, detail="只有订单发布者可以确认成交")
    if order.status != "open":
        raise HTTPException(status_code=400, detail="订单已成交或已关闭")

    updated = state.memory.accept_swap_offer(offer_id)
    return _order_response(updated)


@router.post("/orders/{order_id}/close", response_model=SwapOrderResponse)
async def close_swap_order(
    order_id: str,
    user_id: str = Depends(get_current_user),
) -> SwapOrderResponse:
    """订单发布者手动关闭订单。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    order = state.memory.get_swap_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.maker_id != user_id:
        raise HTTPException(status_code=403, detail="只有订单发布者可以关闭订单")
    if order.status != "open":
        raise HTTPException(status_code=400, detail="订单已成交或已关闭")

    order.status = "closed"
    saved = state.memory.save_swap_order(order)
    return _order_response(saved)


@router.post("/admin/orders/{order_id}/feature", response_model=SwapOrderResponse)
async def feature_swap_order(
    order_id: str,
    request: SwapFeatureRequest,
    _admin: str = Depends(require_admin),
) -> SwapOrderResponse:
    """管理员设置订单精选状态。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    order = state.memory.set_swap_featured(order_id, request.featured)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return _order_response(order)


@router.post("/upload")
async def upload_swap_image(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """上传交换订单配图，保存到 frontend/swap_images/ 目录。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    frontend_dir = Path(__file__).resolve().parent.parent.parent.parent.parent / "frontend"
    images_dir = frontend_dir / "swap_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # 安全检查：只允许图片
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只允许上传图片文件")

    # 扩展名白名单
    suffix = Path(file.filename or "swap.jpg").suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持的图片格式")

    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="图片大小不能超过 10MB")

    # 生成安全文件名：swap_{user_id}_{uuid8}{suffix}
    save_name = f"swap_{user_id}_{uuid.uuid4().hex[:8]}{suffix}"
    save_path = images_dir / save_name
    save_path.write_bytes(content)

    # 生产环境 nginx 的 /static/ 指向部署目录（/var/www/frontend），
    # 运行时上传的文件必须镜像一份到部署目录才能被访问（仓库目录仅供本地开发/测试）
    mirror_upload("swap_images", save_name, content)

    return {"url": f"/static/swap_images/{save_name}"}
