"""投稿路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.memory.models import SubmissionData

router = APIRouter(tags=["submissions"])


class SubmitRequest(BaseModel):
    """投稿请求。"""

    target_actor: str = Field(description="目标演员")


class ReviewRequest(BaseModel):
    """审核请求。"""

    status: str = Field(description="审核结果：adopted / rejected")
    comment: str | None = Field(default=None, description="审核意见")


class SubmissionListResponse(BaseModel):
    """投稿列表响应。"""

    submissions: list[SubmissionData] = Field(description="投稿列表")


@router.post("/scripts/{script_id}/submit", response_model=SubmissionData)
async def submit_script(
    script_id: str,
    request: SubmitRequest,
    user_id: str = Depends(get_current_user),
) -> SubmissionData:
    """将作品投稿给指定演员。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    script = state.memory.load_script(script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    submission = SubmissionData(
        user_id=user_id,
        script_id=script_id,
        target_actor=request.target_actor,
        status="pending",
    )
    return state.memory.save_submission(submission)


@router.get("/submissions", response_model=SubmissionListResponse)
async def list_submissions(
    target_actor: str | None = None,
    status: str | None = None,
    user_id: str = Depends(get_current_user),
) -> SubmissionListResponse:
    """列出当前用户的投稿。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    submissions = state.memory.list_submissions(
        user_id=user_id, target_actor=target_actor, status=status
    )
    return SubmissionListResponse(submissions=submissions)


@router.post("/submissions/{submission_id}/review")
async def review_submission(
    submission_id: str,
    request: ReviewRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, bool]:
    """审核投稿（演员/管理员使用）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    ok = state.memory.review_submission(submission_id, request.status, request.comment)
    if not ok:
        raise HTTPException(status_code=404, detail="投稿不存在")
    return {"success": True}
