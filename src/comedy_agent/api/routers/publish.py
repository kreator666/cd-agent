"""一键发布路由 —— 多平台内容分发。

提供视频上传、平台登录状态检查、一键发布到 B站 等能力。
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.publisher import (
    BilibiliAdapter,
    ContentItem,
    MultiPlatformPublisher,
    PlatformType,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/publish", tags=["publish"])

# 上传文件临时存储目录
_UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "uploads" / "publish"
_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Pydantic 请求/响应模型
# --------------------------------------------------------------------------- #


class UploadResponse(BaseModel):
    """视频上传响应。"""

    success: bool
    video_path: str = Field(description="服务器端临时视频路径")
    filename: str = Field(description="原始文件名")


class PublishRequest(BaseModel):
    """一键发布请求。"""

    title: str = Field(description="视频标题")
    content: str = Field(default="", description="视频描述/正文")
    tags: str = Field(default="", description="标签，逗号分隔")
    video_path: str = Field(description="服务器端临时视频路径")
    platforms: list[str] = Field(default=["bilibili"], description="目标平台列表")
    category: str = Field(default="", description="B站分区名称（可选）")


class PlatformResult(BaseModel):
    """单个平台发布结果。"""

    platform: str
    name: str
    success: bool
    message: str
    url: str | None = None
    content_id: str | None = None


class PublishResponse(BaseModel):
    """一键发布响应。"""

    success: bool
    results: list[PlatformResult]


class LoginStatusResponse(BaseModel):
    """平台登录状态响应。"""

    platform: str
    name: str
    logged_in: bool


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #


def _publisher_for_platforms(platform_values: list[str]) -> MultiPlatformPublisher:
    """根据平台名称构造发布器并注册对应适配器。"""
    publisher = MultiPlatformPublisher()

    platform_mapping: dict[str, PlatformType] = {
        "bilibili": PlatformType.BILIBILI,
        "xiaohongshu": PlatformType.XIAOHONGSHU,
        "douyin": PlatformType.DOUYIN,
        "wechat_video": PlatformType.WECHAT_VIDEO,
    }

    for pv in platform_values:
        platform_type = platform_mapping.get(pv.lower())
        if platform_type == PlatformType.BILIBILI:
            publisher.register_adapter(BilibiliAdapter({"login_method": "qr"}))
        # 其他平台适配器后续按需注册

    return publisher


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #


@router.post("/upload", response_model=UploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
) -> UploadResponse:
    """上传视频文件到服务器临时目录，返回临时路径供发布接口使用。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")

    # 限制常见视频格式
    allowed_exts = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    upload_id = uuid.uuid4().hex
    upload_dir = _UPLOAD_ROOT / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest_path = upload_dir / file.filename
    try:
        with dest_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.exception("上传视频失败")
        raise HTTPException(status_code=500, detail=f"上传失败: {e}") from e
    finally:
        await file.close()

    logger.info("[%s] 视频上传成功: %s -> %s", user_id, file.filename, dest_path)
    return UploadResponse(
        success=True,
        video_path=str(dest_path),
        filename=file.filename,
    )


@router.post("/", response_model=PublishResponse)
async def publish_content(
    request: PublishRequest,
    user_id: str = Depends(get_current_user),
) -> PublishResponse:
    """一键发布内容到指定平台。"""
    if not request.title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    if not request.video_path:
        raise HTTPException(status_code=400, detail="视频路径不能为空")

    video_path = Path(request.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=400, detail=f"视频文件不存在: {request.video_path}")

    tags = [t.strip() for t in request.tags.split(",") if t.strip()]

    # 构造平台特化配置
    platform_extra: dict[PlatformType, dict] = {}
    if request.category:
        platform_extra[PlatformType.BILIBILI] = {"category": request.category}

    content = ContentItem(
        title=request.title,
        content=request.content,
        video_path=str(video_path),
        tags=tags,
        platform_extra=platform_extra,
    )

    publisher = _publisher_for_platforms(request.platforms)
    if not publisher.adapters:
        raise HTTPException(status_code=400, detail="没有可用的平台适配器")

    try:
        results = await publisher.publish_to_all(
            content=content,
            platforms=list(publisher.adapters.keys()),
            sequential=True,
            delay_seconds=5.0,
        )
    except Exception as e:
        logger.exception("一键发布失败")
        raise HTTPException(status_code=500, detail=f"发布失败: {e}") from e
    finally:
        await publisher.cleanup_all()

    platform_results = []
    for platform_type, result in results.items():
        platform_results.append(
            PlatformResult(
                platform=platform_type.value,
                name=platform_type.name,
                success=result.success,
                message=result.message,
                url=result.url,
                content_id=result.content_id,
            )
        )

    overall_success = any(r.success for r in platform_results)
    logger.info(
        "[%s] 一键发布完成: 成功 %s/%s",
        user_id,
        sum(1 for r in platform_results if r.success),
        len(platform_results),
    )
    return PublishResponse(success=overall_success, results=platform_results)


@router.get("/login-status", response_model=list[LoginStatusResponse])
async def check_login_status(
    user_id: str = Depends(get_current_user),
) -> list[LoginStatusResponse]:
    """检查当前已注册平台的登录状态。"""
    publisher = _publisher_for_platforms(["bilibili"])
    status_map = await publisher.check_all_login_status()
    await publisher.cleanup_all()

    return [
        LoginStatusResponse(
            platform=pt.value,
            name=pt.name,
            logged_in=logged_in,
        )
        for pt, logged_in in status_map.items()
    ]
