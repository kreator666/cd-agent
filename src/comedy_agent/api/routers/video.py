"""脱口秀视频生成路由。

提供创建任务、查询进度、获取产物与下载视频的能力。
"""

from __future__ import annotations

import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from comedy_agent.api.state import state
from comedy_agent.auth import get_current_user
from comedy_agent.core.config import settings
from comedy_agent.memory.schema import EvalResult, EvalSession, VideoJob
from comedy_agent.services.video_generator import VideoConfig, VideoGenerator, config_from_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])


# --------------------------------------------------------------------------- #
# Pydantic 请求/响应模型
# --------------------------------------------------------------------------- #


class VideoCreateRequest(BaseModel):
    """创建视频生成任务请求。"""

    result_id: str = Field(description="评测结果 ID")
    style: str = Field(default="illustration", description="视频风格")
    tts_enabled: bool = Field(default=True, description="是否启用配音")
    tts_voice: str = Field(default="zh-CN-XiaoxiaoNeural", description="TTS 音色")
    bgm_enabled: bool = Field(default=False, description="是否启用 BGM")
    pace: str = Field(default="normal", description="节奏: slow / normal / fast")
    max_scenes: int = Field(default=5, ge=2, le=8, description="最大镜头数")


class StageItem(BaseModel):
    """阶段状态项。"""

    name: str
    label: str
    status: str
    message: str


class VideoJobResponse(BaseModel):
    """视频任务响应。"""

    job_id: str
    result_id: str
    status: str
    stage: str
    stages: list[StageItem]
    video_url: str | None = None
    final_video_path: str | None = None
    storyboard: dict[str, Any] | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class VideoListResponse(BaseModel):
    """视频任务列表响应。"""

    jobs: list[VideoJobResponse]


# --------------------------------------------------------------------------- #
# 数据库会话辅助
# --------------------------------------------------------------------------- #


def _db_session() -> Session:
    """获取一个独立的 SQLAlchemy Session。"""
    if state.memory is None or state.memory._store is None:
        raise HTTPException(status_code=503, detail="记忆服务未初始化")
    return state.memory._store._new_session()


def _job_to_response(job: VideoJob) -> VideoJobResponse:
    """将 VideoJob ORM 转为响应模型。"""
    try:
        stages = (
            job.stages
            if isinstance(job.stages, list)
            else [
                {"name": k, "label": _stage_label(k), "status": "pending", "message": ""}
                for k in ["script", "assets", "storyboard", "video", "post"]
            ]
        )
    except Exception:
        stages = []

    video_url = None
    if job.final_video_path and Path(job.final_video_path).exists():
        # 如果配置了静态部署目录，返回可访问 URL；否则返回下载端点
        if settings.static_deploy_dir:
            rel = Path(job.final_video_path).relative_to(
                Path(settings.video_output_dir)
            )
            video_url = f"/static/video/{rel.as_posix()}"
        else:
            video_url = f"/video/jobs/{job.job_id}/download"

    return VideoJobResponse(
        job_id=job.job_id,
        result_id=job.result_id,
        status=job.status,
        stage=job.stage,
        stages=[StageItem(**s) for s in stages],
        video_url=video_url,
        final_video_path=job.final_video_path,
        storyboard=job.storyboard_json,
        error=job.error,
        created_at=job.created_at.isoformat() if job.created_at else "",
        updated_at=job.updated_at.isoformat() if job.updated_at else "",
    )


def _stage_label(name: str) -> str:
    labels = {
        "script": "剧本分镜",
        "assets": "画面资产",
        "storyboard": "分镜预览",
        "video": "视频合成",
        "post": "后期配音",
    }
    return labels.get(name, name)


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #


@router.post("/jobs", response_model=VideoJobResponse)
async def create_video_job(
    request: VideoCreateRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
) -> VideoJobResponse:
    """创建脱口秀视频生成任务。"""
    with _db_session() as session:
        result = (
            session.query(EvalResult)
            .join(EvalSession)
            .filter(EvalResult.result_id == request.result_id, EvalSession.user_id == user_id)
            .first()
        )
        if result is None:
            raise HTTPException(status_code=404, detail="评测结果不存在")
        if result.status != "done" or not result.content:
            raise HTTPException(status_code=400, detail="段子尚未生成完成或内容为空")

        job_id = uuid.uuid4().hex[:16]
        now = datetime.utcnow()
        script_text = result.content or ""

        job = VideoJob(
            job_id=job_id,
            result_id=request.result_id,
            user_id=user_id,
            status="pending",
            stage="script",
            stages=[
                {"name": k, "label": _stage_label(k), "status": "pending", "message": ""}
                for k in ["script", "assets", "storyboard", "video", "post"]
            ],
            config_json=request.model_dump(),
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.commit()
        response = _job_to_response(job)

    background_tasks.add_task(
        _run_video_generation,
        job_id=job_id,
        result_id=request.result_id,
        user_id=user_id,
        script_text=script_text,
        config=request.model_dump(),
    )

    return response


@router.get("/jobs/{job_id}", response_model=VideoJobResponse)
async def get_video_job(
    job_id: str,
    user_id: str = Depends(get_current_user),
) -> VideoJobResponse:
    """查询视频任务状态。"""
    with _db_session() as session:
        job = (
            session.query(VideoJob)
            .filter(VideoJob.job_id == job_id, VideoJob.user_id == user_id)
            .first()
        )
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return _job_to_response(job)


@router.get("/jobs/{job_id}/download")
async def download_video(
    job_id: str,
    user_id: str = Depends(get_current_user),
) -> Any:
    """下载生成的视频。"""
    from fastapi.responses import FileResponse

    with _db_session() as session:
        job = (
            session.query(VideoJob)
            .filter(VideoJob.job_id == job_id, VideoJob.user_id == user_id)
            .first()
        )
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        if not job.final_video_path or not Path(job.final_video_path).exists():
            raise HTTPException(status_code=400, detail="视频尚未生成完成")
        final_path = job.final_video_path

    return FileResponse(
        path=final_path,
        media_type="video/mp4",
        filename=f"standup_{job_id}.mp4",
    )


@router.get("/jobs", response_model=VideoListResponse)
async def list_video_jobs(
    user_id: str = Depends(get_current_user),
    limit: int = 20,
) -> VideoListResponse:
    """列出当前用户的视频任务。"""
    with _db_session() as session:
        jobs = (
            session.query(VideoJob)
            .filter(VideoJob.user_id == user_id)
            .order_by(VideoJob.created_at.desc())
            .limit(limit)
            .all()
        )
        return VideoListResponse(jobs=[_job_to_response(j) for j in jobs])


# --------------------------------------------------------------------------- #
# 后台生成任务
# --------------------------------------------------------------------------- #


def _update_job(
    job_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    stages: list[dict[str, Any]] | None = None,
    script_json: dict[str, Any] | None = None,
    asset_urls: list[str] | None = None,
    storyboard_json: dict[str, Any] | None = None,
    video_path: str | None = None,
    final_video_path: str | None = None,
    tts_path: str | None = None,
    error: str | None = None,
) -> None:
    """更新任务状态与产物。"""
    try:
        with _db_session() as session:
            job = session.query(VideoJob).filter_by(job_id=job_id).first()
            if job is None:
                return
            if status is not None:
                job.status = status
            if stage is not None:
                job.stage = stage
            if stages is not None:
                job.stages = stages
            if script_json is not None:
                job.script_json = script_json
            if asset_urls is not None:
                job.asset_urls = asset_urls
            if storyboard_json is not None:
                job.storyboard_json = storyboard_json
                # 分镜数据同时写入 storyboard
            if video_path is not None:
                job.video_path = video_path
            if final_video_path is not None:
                job.final_video_path = final_video_path
            if tts_path is not None:
                job.tts_path = tts_path
            if error is not None:
                job.error = error
            job.updated_at = datetime.utcnow()
            session.commit()
    except Exception:
        logger.exception("[video-%s] 更新任务状态失败", job_id)


def _run_video_generation(
    job_id: str,
    result_id: str,
    user_id: str,
    script_text: str,
    config: dict[str, Any],
) -> None:
    """后台执行视频生成。"""
    try:
        _update_job(job_id, status="running", stage="script")

        video_config = config_from_dict(config)
        generator = VideoGenerator(
            job_id=job_id,
            result_id=result_id,
            user_id=user_id,
            script_text=script_text,
            config=video_config,
        )

        # 剧本分镜
        generator.split_script()
        _update_job(
            job_id,
            stage="script",
            stages=generator.stage_summary(),
            script_json={"scenes": [{"text": s.text, "order": s.order} for s in generator.scenes]},
        )

        # 画面资产
        generator.generate_assets()
        _update_job(
            job_id,
            stage="assets",
            stages=generator.stage_summary(),
            asset_urls=[s.image_path for s in generator.scenes if s.image_path],
        )

        # 分镜预览
        storyboard = generator.build_storyboard()
        _update_job(
            job_id,
            stage="storyboard",
            stages=generator.stage_summary(),
            storyboard_json=storyboard,
        )

        # 视频合成 + 后期
        final_path = generator.compose_video()
        _update_job(
            job_id,
            status="done",
            stage="post",
            stages=generator.stage_summary(),
            final_video_path=str(final_path),
        )

        # 若配置了静态部署目录，则镜像一份供 /static/ 访问
        if settings.static_deploy_dir:
            _mirror_to_static(final_path)

    except Exception as exc:
        logger.exception("[video-%s] 视频生成失败", job_id)
        _update_job(job_id, status="failed", stage="post", error=f"{type(exc).__name__}: {exc}")


def _mirror_to_static(video_path: Path) -> None:
    """将生成的视频镜像到 nginx 静态部署目录。"""
    try:
        deploy_dir = Path(settings.static_deploy_dir)
        rel = Path(video_path).relative_to(Path(settings.video_output_dir))
        dest = deploy_dir / "video" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video_path, dest)
        logger.info("[video] 镜像视频到静态目录: %s", dest)
    except Exception:
        logger.exception("[video] 镜像视频到静态目录失败")
