"""IP 风格模型路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from comedy_agent.api.state import state
from comedy_agent.memory.models import IPStyleData

router = APIRouter(tags=["ip-styles"])


@router.get("/ip-styles")
async def list_ip_styles(status: str | None = "active") -> list[IPStyleData]:
    """列出 IP 风格模型。"""
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
