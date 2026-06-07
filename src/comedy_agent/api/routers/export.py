"""作品导出路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user

router = APIRouter(tags=["export"])


@router.get("/scripts/{script_id}/export")
async def export_script(
    script_id: str,
    format: str = "txt",
    user_id: str = Depends(get_current_user),
) -> PlainTextResponse:
    """导出作品为文本或 Markdown。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    script = state.memory.load_script(script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="作品不存在")

    content = script.content or ""
    if format == "md":
        title = script.title or "未命名作品"
        content = f"# {title}\n\n{content}"
        media_type = "text/markdown; charset=utf-8"
        filename = f"{title}.md"
    else:
        media_type = "text/plain; charset=utf-8"
        filename = f"{script.title or 'script'}.txt"

    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
