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
    """用户登录，返回 JWT token。"""
    store = SQLMemoryStore()
    hashed = store.get_user_password_hash(request.user_id)
    if hashed is None:
        raise HTTPException(status_code=401, detail="用户不存在或密码错误")
    if not verify_password(request.password, hashed):
        raise HTTPException(status_code=401, detail="用户不存在或密码错误")

    token = create_access_token(request.user_id)
    return TokenResponse(access_token=token, user_id=request.user_id)


class UserDetailResponse(BaseModel):
    """用户详细信息响应。"""

    user_id: str = Field(description="用户唯一标识")
    nickname: str | None = Field(default=None, description="用户昵称")
    bio: str | None = Field(default=None, description="个人简介")
    tags: list[str] | None = Field(default=None, description="兴趣标签")
    avatar_url: str | None = Field(default=None, description="头像 URL")
    follower_count: int = Field(default=0, description="粉丝数")
    following_count: int = Field(default=0, description="关注数")
    created_at: str | None = Field(default=None, description="创建时间")


class UpdateProfileRequest(BaseModel):
    """更新个人信息请求。"""

    nickname: str | None = Field(default=None, description="昵称")
    bio: str | None = Field(default=None, description="个人简介")
    tags: list[str] | None = Field(default=None, description="兴趣标签")
    avatar_url: str | None = Field(default=None, description="头像 URL")


@router.get("/me", response_model=UserDetailResponse)
async def me(user_id: str = Depends(get_current_user)) -> UserDetailResponse:
    """获取当前登录用户信息（含粉丝数、关注数）。"""
    store = SQLMemoryStore()
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserDetailResponse(
        user_id=user.user_id,
        nickname=user.nickname,
        bio=user.bio,
        tags=user.tags,
        avatar_url=user.avatar_url,
        follower_count=store.count_followers(user_id),
        following_count=store.count_following(user_id),
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.put("/me", response_model=UserDetailResponse)
async def update_me(
    request: UpdateProfileRequest,
    user_id: str = Depends(get_current_user),
) -> UserDetailResponse:
    """更新当前登录用户个人信息。"""
    store = SQLMemoryStore()
    user = store.update_user_profile(
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
        follower_count=store.count_followers(user_id),
        following_count=store.count_following(user_id),
        created_at=user.created_at.isoformat() if user.created_at else None,
    )
