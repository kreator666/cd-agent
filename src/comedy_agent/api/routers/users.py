"""用户关注路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.memory.models import UserProfileData

router = APIRouter(tags=["users"])


class FollowResponse(BaseModel):
    """关注响应。"""

    success: bool = Field(description="是否成功")
    follower_count: int = Field(default=0, description="被关注者当前粉丝数")


class UserListResponse(BaseModel):
    """用户列表响应。"""

    users: list[UserProfileData] = Field(description="用户列表")
    count: int = Field(description="总数")


@router.post("/users/{user_id}/follow", response_model=FollowResponse)
async def follow_user(
    user_id: str,
    current_user_id: str = Depends(get_current_user),
) -> FollowResponse:
    """关注指定用户。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    if user_id == current_user_id:
        raise HTTPException(status_code=400, detail="不能关注自己")
    target = state.memory.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    state.memory.follow(current_user_id, user_id)
    count = state.memory.count_followers(user_id)
    return FollowResponse(success=True, follower_count=count)


@router.post("/users/{user_id}/unfollow", response_model=FollowResponse)
async def unfollow_user(
    user_id: str,
    current_user_id: str = Depends(get_current_user),
) -> FollowResponse:
    """取消关注指定用户。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    ok = state.memory.unfollow(current_user_id, user_id)
    count = state.memory.count_followers(user_id)
    return FollowResponse(success=ok, follower_count=count)


@router.get("/users/{user_id}/followers", response_model=UserListResponse)
async def list_followers(user_id: str) -> UserListResponse:
    """获取指定用户的粉丝列表。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    users = state.memory.list_followers(user_id)
    return UserListResponse(users=users, count=len(users))


@router.get("/users/{user_id}/following", response_model=UserListResponse)
async def list_following(user_id: str) -> UserListResponse:
    """获取指定用户的关注列表。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    users = state.memory.list_following(user_id)
    return UserListResponse(users=users, count=len(users))


@router.get("/users/{user_id}")
async def get_user_profile(user_id: str) -> dict:
    """获取指定用户的公开资料。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    user = state.memory.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "user_id": user.user_id,
        "nickname": user.nickname,
        "bio": user.bio,
        "tags": user.tags,
        "avatar_url": user.avatar_url,
        "is_verified": user.is_verified,
        "follower_count": state.memory.count_followers(user_id),
        "following_count": state.memory.count_following(user_id),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
