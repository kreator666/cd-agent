"""钱包与 Token 账户路由。"""

from __future__ import annotations

from typing import Any

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
