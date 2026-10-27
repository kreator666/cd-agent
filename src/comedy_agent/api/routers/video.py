"""脱口秀视频生成路由。

提供创建任务、分阶段运行、人工编辑、AI 辅助修改与列表查询的能力。
"""

from __future__ import annotations

import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from comedy_agent.api.state import state
from comedy_agent.auth import get_current_user
from comedy_agent.core.config import settings
from comedy_agent.memory.schema import EvalResult, EvalSession, VideoJob
from comedy_agent.services.video_generator import (
    VideoConfig,
    VideoGenerator,
    config_from_dict,
    reconstruct_generator,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["video"])

STAGE_ORDER = ["script", "assets", "storyboard", "video", "post"]


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
    result_content: str | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class VideoListResponse(BaseModel):
    """视频任务列表响应。"""

    jobs: list[VideoJobResponse]


class StageEditRequest(BaseModel):
    """编辑阶段数据请求。"""

    scenes: list[dict[str, Any]] | None = None
    tts_voice: str | None = None
    durations: dict[str, float] | None = None


class StageAiModifyRequest(BaseModel):
    """AI 辅助修改请求。"""

    instruction: str = Field(default="", description="优化指令")


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
                for k in STAGE_ORDER
            ]
        )
    except Exception:
        stages = []

    video_url = None
    if job.final_video_path and Path(job.final_video_path).exists():
        # 统一使用 /static/video/... 提供播放/下载，避免 /video/jobs/.../download 需要鉴权
        rel = Path(job.final_video_path).relative_to(Path(settings.video_output_dir))
        video_url = f"/static/video/{rel.as_posix()}"

    return VideoJobResponse(
        job_id=job.job_id,
        result_id=job.result_id,
        status=job.status,
        stage=job.stage,
        stages=[StageItem(**s) for s in stages],
        video_url=video_url,
        final_video_path=job.final_video_path,
        storyboard=job.storyboard_json,
        result_content=job.result.content if job.result is not None else None,
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
    user_id: str = Depends(get_current_user),
) -> VideoJobResponse:
    """创建脱口秀视频生成任务（分阶段执行，不自动跑完全部流程）。"""
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

        job = VideoJob(
            job_id=job_id,
            result_id=request.result_id,
            user_id=user_id,
            status="pending",
            stage="script",
            stages=[
                {"name": k, "label": _stage_label(k), "status": "pending", "message": ""}
                for k in STAGE_ORDER
            ],
            config_json=request.model_dump(),
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        session.commit()
        return _job_to_response(job)


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
    """下载生成的视频（保留鉴权接口，供显式下载场景使用）。"""
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
# 分阶段执行 / 编辑 / AI 修改
# --------------------------------------------------------------------------- #


def _load_job(job_id: str, user_id: str) -> VideoJob:
    """加载并校验任务归属。"""
    with _db_session() as session:
        job = (
            session.query(VideoJob)
            .filter(VideoJob.job_id == job_id, VideoJob.user_id == user_id)
            .first()
        )
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return job


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
    config_json: dict[str, Any] | None = None,
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
            if video_path is not None:
                job.video_path = video_path
            if final_video_path is not None:
                job.final_video_path = final_video_path
            if tts_path is not None:
                job.tts_path = tts_path
            if config_json is not None:
                job.config_json = config_json
            if error is not None:
                job.error = error
            job.updated_at = datetime.utcnow()
            session.commit()
    except Exception:
        logger.exception("[video-%s] 更新任务状态失败", job_id)


def _sync_generator_state(gen: VideoGenerator, job_id: str) -> None:
    """将生成器当前状态同步到数据库。"""
    _update_job(
        job_id,
        script_json=gen.script_json(),
        asset_urls=gen.asset_urls(),
        storyboard_json=gen.storyboard_json(),
        stages=gen.stage_summary(),
    )


@router.post("/jobs/{job_id}/stage/{stage_name}/run", response_model=VideoJobResponse)
async def run_stage(
    job_id: str,
    stage_name: str,
    user_id: str = Depends(get_current_user),
) -> VideoJobResponse:
    """运行指定阶段。"""
    if stage_name not in STAGE_ORDER:
        raise HTTPException(status_code=400, detail=f"未知阶段: {stage_name}")

    job = _load_job(job_id, user_id)
    try:
        _update_job(job_id, status="running")
        gen = reconstruct_generator(job)

        if stage_name == "script":
            gen.split_script()
            _sync_generator_state(gen, job_id)
            _update_job(job_id, stage="script", status="pending")

        elif stage_name == "assets":
            if not gen.scenes:
                gen.split_script()
            gen.generate_assets()
            _sync_generator_state(gen, job_id)
            _update_job(job_id, stage="assets", status="pending")

        elif stage_name == "storyboard":
            if not gen.scenes:
                gen.split_script()
                gen.generate_assets()
            gen.build_storyboard()
            _sync_generator_state(gen, job_id)
            _update_job(job_id, stage="storyboard", status="pending")

        elif stage_name == "video":
            if not gen.scenes:
                gen.split_script()
                gen.generate_assets()
                gen.build_storyboard()
            silent_path = gen.compose_silent_video()
            _sync_generator_state(gen, job_id)
            _update_job(
                job_id,
                stage="video",
                status="pending",
                video_path=str(silent_path),
            )

        elif stage_name == "post":
            final_path = gen.add_post_audio()
            _sync_generator_state(gen, job_id)
            _update_job(
                job_id,
                status="done",
                stage="post",
                final_video_path=str(final_path),
                video_path=str(gen.output_dir / "silent.mp4"),
            )
            if settings.static_deploy_dir:
                _mirror_to_static(final_path)

        return _job_to_response(_load_job(job_id, user_id))
    except Exception as exc:
        logger.exception("[video-%s] 阶段 %s 运行失败", job_id, stage_name)
        _update_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/jobs/{job_id}/stage/{stage_name}/edit", response_model=VideoJobResponse)
async def edit_stage(
    job_id: str,
    stage_name: str,
    request: StageEditRequest,
    user_id: str = Depends(get_current_user),
) -> VideoJobResponse:
    """人工编辑指定阶段产物。"""
    if stage_name not in STAGE_ORDER:
        raise HTTPException(status_code=400, detail=f"未知阶段: {stage_name}")

    job = _load_job(job_id, user_id)
    try:
        gen = reconstruct_generator(job)

        if stage_name == "script" and request.scenes:
            for item in request.scenes:
                order = int(item.get("order", -1))
                if order < 0:
                    continue
                if "text" in item:
                    gen.update_scene_text(order, item["text"])
                if "image_prompt" in item:
                    gen.update_scene_prompt(order, item["image_prompt"])

        elif stage_name == "assets" and request.scenes:
            for item in request.scenes:
                order = int(item.get("order", -1))
                if order < 0:
                    continue
                if "image_prompt" in item:
                    gen.update_scene_prompt(order, item["image_prompt"])
                if item.get("regenerate"):
                    gen.regenerate_scene_image(order)
                if item.get("image_path"):
                    gen.set_scene_image(order, item["image_path"])

        elif stage_name == "storyboard" and request.durations:
            for order_str, duration in (request.durations or {}).items():
                gen.set_scene_duration(int(order_str), float(duration))

        elif stage_name == "post" and request.tts_voice:
            gen.set_tts_voice(request.tts_voice)
            _update_job(job_id, config_json=gen.config.__dict__)

        _sync_generator_state(gen, job_id)
        return _job_to_response(_load_job(job_id, user_id))
    except Exception as exc:
        logger.exception("[video-%s] 阶段 %s 编辑失败", job_id, stage_name)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/jobs/{job_id}/stage/{stage_name}/ai-modify", response_model=VideoJobResponse)
async def ai_modify_stage(
    job_id: str,
    stage_name: str,
    request: StageAiModifyRequest,
    user_id: str = Depends(get_current_user),
) -> VideoJobResponse:
    """使用 AI 辅助修改指定阶段产物。"""
    if stage_name not in ("script", "assets"):
        raise HTTPException(status_code=400, detail="仅支持 script / assets 阶段的 AI 修改")

    job = _load_job(job_id, user_id)
    try:
        gen = reconstruct_generator(job)
        if stage_name == "script":
            gen.ai_modify_script(request.instruction)
        elif stage_name == "assets":
            gen.ai_modify_assets(request.instruction)
        _sync_generator_state(gen, job_id)
        return _job_to_response(_load_job(job_id, user_id))
    except Exception as exc:
        logger.exception("[video-%s] 阶段 %s AI 修改失败", job_id, stage_name)
        raise HTTPException(status_code=500, detail=str(exc))


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #


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
