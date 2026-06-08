"""管理控制台路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.memory.models import BannedWordData, IPStyleData

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
