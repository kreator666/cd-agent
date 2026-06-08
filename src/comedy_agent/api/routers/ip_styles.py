"""IP 风格模型路由（PRD v2 扩展为 IP 角色）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.memory.models import IPStyleData

router = APIRouter(tags=["ip-styles"])


class TryStyleRequest(BaseModel):
    """快捷试用风格请求。"""

    text: str = Field(description="需要试用的原始文本")
    intensity: str = Field(default="medium", description="加梗强度")


@router.get("/ip-styles")
async def list_ip_styles(status: str | None = "active") -> list[IPStyleData]:
    """列出 IP 风格模型。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    return state.memory.list_ip_styles(status=status)


@router.get("/ip-roles")
async def list_ip_roles(status: str | None = "active") -> list[IPStyleData]:
    """列出 IP 角色（与 /ip-styles 同义，面向前端极速版）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    return state.memory.list_ip_styles(status=status)


@router.get("/ip-styles/{style_id}")
async def get_ip_style(style_id: str) -> IPStyleData:
    """获取 IP 风格模型详情。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    style = state.memory.load_ip_style(style_id)
    if style is None:
        raise HTTPException(status_code=404, detail="IP 风格不存在")
    return style


@router.get("/ip-roles/{role_id}")
async def get_ip_role(role_id: str) -> IPStyleData:
    """获取 IP 角色详情（与 /ip-styles/{id} 同义）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    style = state.memory.load_ip_style(role_id)
    if style is None:
        raise HTTPException(status_code=404, detail="IP 角色不存在")
    return style


@router.post("/ip-roles/{role_id}/try")
async def try_ip_role(
    role_id: str,
    request: TryStyleRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """快捷试用该 IP 角色风格生成。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    role = state.memory.load_ip_style(role_id)
    if role is None or role.status != "active":
        raise HTTPException(status_code=404, detail="IP 角色不存在或未激活")

    # 内部调用 add_salt skill，注入角色风格
    prompt = (
        f"使用 add_salt 技能 来对以下文本进行幽默润色。\n\n"
        f"原文：{request.text}\n"
        f"强度：{request.intensity}\n"
        f"角色风格：{role.prompt_snippet}"
    )
    result = state.orch.run(prompt, user_id=user_id)
    polished = result.get("output", "")

    # 更新使用次数
    role.usage_count = (role.usage_count or 0) + 1
    state.memory.save_ip_style(role)

    return {
        "original": request.text,
        "polished": polished,
        "role_id": role_id,
        "actor_name": role.actor_name,
        "avatar_url": role.avatar_url,
    }
