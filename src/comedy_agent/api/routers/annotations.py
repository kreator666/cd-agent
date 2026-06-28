"""标注与反馈接口。

提供把 AI 生成内容标注为 Few-shot 示例、批量导入标注文件、
以及记录消息/Artifact 级反馈事件的能力。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth import get_current_user
from comedy_agent.core.annotation import AnnotatedExample, build_embedding_text
from comedy_agent.core.example_retriever import ingest_annotations
from comedy_agent.memory.models import FeedbackEventData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/annotations", tags=["annotations"])


# ------------------------------------------------------------------ #
# 请求 / 响应模型
# ------------------------------------------------------------------ #
class AnnotationCreateRequest(BaseModel):
    """单条标注创建请求。"""

    example_id: str | None = Field(default=None, description="示例 ID，留空自动生成")
    content: str = Field(description="完整段子文本")
    setup: str = Field(default="", description="铺垫部分")
    punchline: str = Field(default="", description="笑点/反转")
    callback: bool = Field(default=False, description="是否包含 callback")
    callback_to: str | None = Field(default=None, description="callback 呼应对象")
    tags: list[str] = Field(default_factory=list, description="关键词标签")
    topic: str = Field(default="", description="核心话题")
    style: str = Field(default="", description="风格")
    kind: str = Field(default="standup", description="喜剧种类")
    structure_type: str = Field(default="script", description="结构类型")
    humor_score: float = Field(default=5.0, ge=1.0, le=10.0, description="幽默评分 1-10")
    source: str = Field(default="", description="来源标识")


class AnnotationCreateResponse(BaseModel):
    """单条标注创建响应。"""

    example_id: str = Field(description="示例 ID")
    collection: str = Field(description="写入的集合名")


class AnnotationIngestRequest(BaseModel):
    """批量标注导入请求。"""

    examples: list[AnnotatedExample] = Field(description="标注示例列表")
    collection: str | None = Field(default=None, description="自定义集合名，留空使用用户个人库")


class AnnotationIngestResponse(BaseModel):
    """批量标注导入响应。"""

    ingested_count: int = Field(description="成功写入条数")
    ids: list[str] = Field(description="写入的文档 ID 列表")
    collection: str = Field(description="实际写入的集合名")


class FeedbackMessageRequest(BaseModel):
    """消息/Artifact 反馈请求。"""

    session_id: str | None = Field(default=None, description="会话 ID")
    target_type: str = Field(description="反馈对象类型：message / artifact")
    target_id: str = Field(description="对象标识")
    rating: int = Field(description="1 赞 / -1 踩 / 0 撤销")
    comment: str | None = Field(default=None, description="文字反馈")
    payload: dict[str, Any] | None = Field(default=None, description="附加 JSON")


class FeedbackMessageResponse(BaseModel):
    """消息/Artifact 反馈响应。"""

    event_id: str = Field(description="反馈事件 ID")
    created_at: str | None = Field(default=None, description="创建时间 ISO 格式")


class FeedbackEventOut(BaseModel):
    """反馈事件列表项。"""

    event_id: str
    session_id: str | None
    target_type: str
    target_id: str
    rating: int
    comment: str | None
    ingested: bool
    created_at: str | None


class FeedbackEventsResponse(BaseModel):
    """反馈事件列表响应。"""

    events: list[FeedbackEventOut]


# ------------------------------------------------------------------ #
# 接口实现
# ------------------------------------------------------------------ #
def _ensure_embedding_text(example: AnnotatedExample) -> AnnotatedExample:
    """补全 embedding_text，避免前端未填充时写入空向量。"""
    if not example.embedding_text:
        example.embedding_text = build_embedding_text(example)
    return example


@router.post("/ingest", response_model=AnnotationIngestResponse)
async def ingest_annotations_endpoint(
    request: AnnotationIngestRequest,
    user_id: str = Depends(get_current_user),
) -> AnnotationIngestResponse:
    """批量导入标注示例到向量库（默认写入用户个人库）。"""
    examples = [_ensure_embedding_text(ex) for ex in request.examples]
    collection = request.collection
    try:
        ids = ingest_annotations(examples, user_id=user_id, collection_name=collection)
    except Exception as e:
        logger.warning("批量导入标注失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"导入失败: {e}") from e

    # 推断实际集合名，与 example_retriever 逻辑一致
    actual_collection = collection or (
        f"user_knowledge_{user_id}" if user_id else "comedy_knowledge"
    )
    return AnnotationIngestResponse(
        ingested_count=len(ids),
        ids=ids,
        collection=actual_collection,
    )


@router.post("", response_model=AnnotationCreateResponse)
async def create_annotation(
    request: AnnotationCreateRequest,
    user_id: str = Depends(get_current_user),
) -> AnnotationCreateResponse:
    """从 UI 创建单条标注示例并写入向量库。"""
    if not request.content or not request.content.strip():
        raise HTTPException(status_code=422, detail="content 不能为空")
    data = {
        "content": request.content,
        "setup": request.setup,
        "punchline": request.punchline,
        "callback": request.callback,
        "callback_to": request.callback_to,
        "tags": request.tags,
        "topic": request.topic,
        "style": request.style,
        "kind": request.kind,
        "structure_type": request.structure_type,
        "humor_score": request.humor_score,
        "source": request.source,
    }
    if request.example_id:
        data["example_id"] = request.example_id
    example = AnnotatedExample(**data)
    example = _ensure_embedding_text(example)
    try:
        ids = ingest_annotations([example], user_id=user_id)
    except Exception as e:
        logger.warning("单条标注创建失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建失败: {e}") from e

    collection = f"user_knowledge_{user_id}" if user_id else "comedy_knowledge"
    return AnnotationCreateResponse(example_id=example.example_id, collection=collection)


@router.post("/feedback/message", response_model=FeedbackMessageResponse)
async def create_feedback_message(
    request: FeedbackMessageRequest,
    user_id: str = Depends(get_current_user),
) -> FeedbackMessageResponse:
    """记录消息/Artifact 级反馈事件。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    if request.rating not in (-1, 0, 1):
        raise HTTPException(status_code=422, detail="rating 必须是 1、-1 或 0")

    event = FeedbackEventData(
        user_id=user_id,
        session_id=request.session_id,
        target_type=request.target_type,
        target_id=request.target_id,
        rating=request.rating,
        comment=request.comment,
        payload=request.payload,
    )
    saved = state.memory.save_feedback_event(event)
    return FeedbackMessageResponse(
        event_id=saved.event_id,
        created_at=saved.created_at.isoformat() if saved.created_at else None,
    )


@router.get("/feedback/events", response_model=FeedbackEventsResponse)
async def list_feedback_events(
    target_type: str | None = None,
    ingested: bool | None = None,
    limit: int = 100,
    user_id: str = Depends(get_current_user),
) -> FeedbackEventsResponse:
    """列出当前用户的反馈事件。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    events = state.memory.list_feedback_events(
        user_id=user_id,
        target_type=target_type,
        ingested=ingested,
        limit=limit,
    )
    return FeedbackEventsResponse(
        events=[
            FeedbackEventOut(
                event_id=e.event_id,
                session_id=e.session_id,
                target_type=e.target_type,
                target_id=e.target_id,
                rating=e.rating,
                comment=e.comment,
                ingested=e.ingested,
                created_at=e.created_at.isoformat() if e.created_at else None,
            )
            for e in events
        ]
    )
