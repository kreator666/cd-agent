"""认证路由 —— 注册、登录、获取当前用户。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from comedy_agent.core.config import settings
from comedy_agent.memory.medium_term import SQLMemoryStore

router = APIRouter(tags=["auth"])

# ------------------------------------------------------------------ #
# 请求/响应模型
# ------------------------------------------------------------------ #


class RegisterRequest(BaseModel):
    """注册请求。"""

    user_id: str = Field(description="用户唯一标识", min_length=1, max_length=64)
    password: str = Field(description="密码", min_length=4)
    nickname: str | None = Field(default=None, description="昵称")


class LoginRequest(BaseModel):
    """登录请求。"""

    user_id: str = Field(description="用户唯一标识")
    password: str = Field(description="密码")


class TokenResponse(BaseModel):
    """登录成功响应。"""

    access_token: str = Field(description="JWT access token")
    token_type: str = Field(default="bearer", description="Token 类型")
    user_id: str = Field(description="用户唯一标识")


class UserResponse(BaseModel):
    """用户信息响应。"""

    user_id: str = Field(description="用户唯一标识")
    nickname: str | None = Field(default=None, description="昵称")


# ------------------------------------------------------------------ #
# 路由
# ------------------------------------------------------------------ #


@router.post("/register", response_model=UserResponse)
async def register(request: RegisterRequest) -> UserResponse:
    """用户注册。"""
    store = SQLMemoryStore()
    try:
        hashed = hash_password(request.password)
        user = store.create_user(
            user_id=request.user_id,
            password_hash=hashed,
            nickname=request.nickname,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return UserResponse(user_id=user.user_id, nickname=user.nickname)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest) -> TokenResponse:
    """用户登录，返回 JWT token。

    管理员用户（ADMIN_USER_ID）的密码优先从 .env 读取，不依赖数据库中的哈希。
    """
    store = SQLMemoryStore()

    # 管理员账号：密码从 .env 读取，db 中有没有记录都不影响登录
    if request.user_id == settings.admin_user_id:
        admin_hash = hash_password(settings.admin_password)
        if not verify_password(request.password, admin_hash):
            raise HTTPException(status_code=401, detail="用户不存在或密码错误")
        token = create_access_token(request.user_id)
        return TokenResponse(access_token=token, user_id=request.user_id)

    hashed = store.get_user_password_hash(request.user_id)
    if hashed is None:
        raise HTTPException(status_code=401, detail="用户不存在或密码错误")
    if not verify_password(request.password, hashed):
        raise HTTPException(status_code=401, detail="用户不存在或密码错误")

    token = create_access_token(request.user_id)
    return TokenResponse(access_token=token, user_id=request.user_id)



