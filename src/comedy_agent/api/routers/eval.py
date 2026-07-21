"""笑果评测 API —— 四维度输入 + Skill 生成 + 评分。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from comedy_agent.api.state import state
from comedy_agent.auth import get_current_user
from comedy_agent.core.config import settings
from comedy_agent.memory.schema import (
    EvalResult,
    EvalSession,
    JokeComment,
    JokeRating,
    UserProfile,
)
from comedy_agent.skills.loader import load_skill_config, load_single_skill
from comedy_agent.skills.prompt_sections import (
    parse_sections,
    section_id_from_title,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["eval"])

# --------------------------------------------------------------------------- #
# Pydantic 请求/响应模型
# --------------------------------------------------------------------------- #


class SectionItem(BaseModel):
    """章节模板项。"""

    id: str = Field(description="章节稳定 ID")
    title: str = Field(description="章节标题")
    body: str = Field(description="章节正文")


class SkillSectionsResponse(BaseModel):
    """Skill 章节模板响应。"""

    skill_name: str
    intro: str = Field(description="固定开头（角色定义等）")
    outro: str = Field(description="固定结尾（最终原则、输出约束等）")
    sections: list[SectionItem]


class EvalCreateRequest(BaseModel):
    """创建评测会话请求。"""

    skill_name: str = Field(default="standup_focused", description="Skill 名称")
    model: str = Field(default="deepseek-v3", description="模型名称")
    topic: str = Field(description="话题")
    attitude: str = Field(description="态度")
    bias: str = Field(description="偏见")
    emotion: str = Field(description="情绪")
    duration: int = Field(default=3, description="时长（分钟）")


class EvalCreateResponse(BaseModel):
    """创建评测会话响应。"""

    session_id: str
    status: str
    total: int


class EvalResultItem(BaseModel):
    """单个评测结果。"""

    id: str
    section_id: str
    section_title: str
    combo_id: str | None = None
    combo_sections: list[dict[str, str]] | None = None
    content: str | None
    status: str
    rating: str | None
    is_published: bool
    model: str
    created_at: str
    completed_at: str | None


class EvalSessionResponse(BaseModel):
    """评测会话详情响应。"""

    session_id: str
    skill_name: str
    model: str
    status: str
    inputs: dict[str, Any]
    total: int
    completed: int
    rated: int
    top_count: int
    results: list[EvalResultItem]


class EvalListResponse(BaseModel):
    """评测会话列表响应。"""

    sessions: list[dict[str, Any]]


class EvalRateRequest(BaseModel):
    """评分请求。"""

    rating: str = Field(description="bad / ok / top")


class EvalRateResponse(BaseModel):
    """评分响应。"""

    success: bool


class PublishResponse(BaseModel):
    """发布/取消发布响应。"""

    success: bool


class PublicRateRequest(BaseModel):
    """路人评分请求。"""

    score: int = Field(ge=0, le=10, description="路人评分 0-10")


class PublicRateResponse(BaseModel):
    """路人评分响应。"""

    success: bool
    average_score: float | None = None
    rating_count: int = 0


class CommentRequest(BaseModel):
    """发表评论请求。"""

    content: str = Field(min_length=1, max_length=2000, description="点评内容")

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        value = value.strip()
        if len(value) == 0:
            raise ValueError("点评内容不能为空")
        return value


class CommentItem(BaseModel):
    """点评项。"""

    comment_id: str
    user_id: str
    nickname: str | None
    content: str
    created_at: str


class CommentListResponse(BaseModel):
    """点评列表响应。"""

    comments: list[CommentItem]
    total: int


class SquareJokeItem(BaseModel):
    """广场段子列表项。"""

    result_id: str
    author_id: str
    author_nickname: str | None
    section_title: str
    content: str
    model: str
    author_rating: str | None
    author_score: float | None
    average_score: float | None
    rating_count: int
    comment_count: int
    published_at: str
    hot_score: float


class SquareListResponse(BaseModel):
    """广场列表响应。"""

    jokes: list[SquareJokeItem]
    total: int
    page: int
    page_size: int


class SquareJokeDetail(BaseModel):
    """广场段子详情。"""

    result_id: str
    author_id: str
    author_nickname: str | None
    section_title: str
    content: str
    model: str
    inputs: dict[str, Any]
    author_rating: str | None
    author_score: float | None
    average_score: float | None
    rating_count: int
    comment_count: int
    my_score: int | None
    published_at: str


# --------------------------------------------------------------------------- #
# 数据库会话辅助
# --------------------------------------------------------------------------- #


def _db_session() -> Session:
    """获取一个独立的 SQLAlchemy Session。"""
    if state.memory is None or state.memory._store is None:
        raise HTTPException(status_code=503, detail="记忆服务未初始化")
    return state.memory._store._new_session()


# --------------------------------------------------------------------------- #
# 章节模板接口
# --------------------------------------------------------------------------- #


@router.get("/skills/{skill_name}/sections", response_model=SkillSectionsResponse)
async def get_skill_sections(
    skill_name: str,
    user_id: str = Depends(get_current_user),
) -> SkillSectionsResponse:
    """获取指定 Skill 的可组合章节模板。"""
    skill_dir = Path(settings.skills_dir) / skill_name
    if not skill_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")

    config = load_skill_config(skill_dir)
    if config is None:
        raise HTTPException(status_code=404, detail=f"无法加载 Skill '{skill_name}'")

    if not config.system_prompt:
        raise HTTPException(
            status_code=404, detail=f"Skill '{skill_name}' 没有系统提示词"
        )

    intro, middle, outro = parse_sections(config.system_prompt)
    sections = [
        SectionItem(
            id=section_id_from_title(title),
            title=title,
            body=body,
        )
        for title, body in middle
    ]

    return SkillSectionsResponse(
        skill_name=skill_name,
        intro=intro,
        outro=outro,
        sections=sections,
    )


# --------------------------------------------------------------------------- #
# 评测会话接口
# --------------------------------------------------------------------------- #


@router.post("/sessions", response_model=EvalCreateResponse)
async def create_eval_session(
    request: EvalCreateRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
) -> EvalCreateResponse:
    """创建评测会话并后台生成结果。"""
    if not request.topic or not request.attitude or not request.emotion:
        raise HTTPException(status_code=400, detail="请填写话题、态度和情绪")

    session_id = uuid.uuid4().hex[:16]
    now = datetime.utcnow()

    with _db_session() as session:
        eval_session = EvalSession(
            session_id=session_id,
            user_id=user_id,
            skill_name=request.skill_name,
            model=request.model,
            topic=request.topic,
            attitude=request.attitude,
            bias=request.bias,
            emotion=request.emotion,
            duration=request.duration,
            status="running",
            total=1,
            created_at=now,
            updated_at=now,
        )
        session.add(eval_session)

        result = EvalResult(
            result_id=uuid.uuid4().hex[:16],
            session_id=session_id,
            section_id="full",
            section_title=request.topic,
            section_body="",
            combo_id=None,
            combo_sections=[],
            status="pending",
            model=request.model,
            created_at=now,
        )
        session.add(result)
        session.commit()

    background_tasks.add_task(
        _run_eval_generation,
        session_id=session_id,
        user_id=user_id,
        skill_name=request.skill_name,
        model=request.model,
        topic=request.topic,
        attitude=request.attitude,
        bias=request.bias,
        emotion=request.emotion,
        duration=request.duration,
    )

    return EvalCreateResponse(
        session_id=session_id,
        status="running",
        total=1,
    )


@router.get("/sessions/{session_id}", response_model=EvalSessionResponse)
async def get_eval_session(
    session_id: str,
    user_id: str = Depends(get_current_user),
) -> EvalSessionResponse:
    """获取评测会话详情与结果。"""
    with _db_session() as session:
        eval_session = (
            session.query(EvalSession)
            .filter_by(session_id=session_id, user_id=user_id)
            .first()
        )
        if eval_session is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        results = (
            session.query(EvalResult)
            .filter_by(session_id=session_id)
            .order_by(EvalResult.created_at)
            .all()
        )

        completed = sum(1 for r in results if r.status in ("done", "failed"))
        rated = sum(1 for r in results if r.rating is not None)
        top_count = sum(1 for r in results if r.rating == "top")

        return EvalSessionResponse(
            session_id=eval_session.session_id,
            skill_name=eval_session.skill_name,
            model=eval_session.model,
            status=eval_session.status,
            inputs={
                "topic": eval_session.topic,
                "attitude": eval_session.attitude,
                "bias": eval_session.bias,
                "emotion": eval_session.emotion,
                "duration": eval_session.duration,
            },
            total=eval_session.total,
            completed=completed,
            rated=rated,
            top_count=top_count,
            results=[
                EvalResultItem(
                    id=r.result_id,
                    section_id=r.section_id,
                    section_title=r.section_title,
                    combo_id=r.combo_id,
                    combo_sections=r.combo_sections,
                    content=r.content,
                    status=r.status,
                    rating=r.rating,
                    is_published=r.is_published,
                    model=r.model,
                    created_at=r.created_at.isoformat() if r.created_at else "",
                    completed_at=r.completed_at.isoformat() if r.completed_at else None,
                )
                for r in results
            ],
        )


@router.get("/sessions", response_model=EvalListResponse)
async def list_eval_sessions(
    user_id: str = Depends(get_current_user),
    limit: int = 20,
) -> EvalListResponse:
    """列出当前用户的评测会话。"""
    with _db_session() as session:
        sessions = (
            session.query(EvalSession)
            .filter_by(user_id=user_id)
            .order_by(EvalSession.created_at.desc())
            .limit(limit)
            .all()
        )

        result = []
        for s in sessions:
            results = (
                session.query(EvalResult).filter_by(session_id=s.session_id).all()
            )
            result.append(
                {
                    "session_id": s.session_id,
                    "skill_name": s.skill_name,
                    "model": s.model,
                    "topic": s.topic,
                    "status": s.status,
                    "total": s.total,
                    "rated": sum(1 for r in results if r.rating is not None),
                    "top_count": sum(1 for r in results if r.rating == "top"),
                    "created_at": s.created_at.isoformat() if s.created_at else "",
                }
            )

        return EvalListResponse(sessions=result)


@router.post("/results/{result_id}/rate", response_model=EvalRateResponse)
async def rate_eval_result(
    result_id: str,
    request: EvalRateRequest,
    user_id: str = Depends(get_current_user),
) -> EvalRateResponse:
    """对单个评测结果评分。"""
    if request.rating not in ("bad", "ok", "top"):
        raise HTTPException(status_code=400, detail="评分必须是 bad / ok / top 之一")

    with _db_session() as session:
        result = (
            session.query(EvalResult)
            .join(EvalSession)
            .filter(EvalResult.result_id == result_id, EvalSession.user_id == user_id)
            .first()
        )
        if result is None:
            raise HTTPException(status_code=404, detail="结果不存在")

        result.rating = request.rating
        session.commit()

    return EvalRateResponse(success=True)


# --------------------------------------------------------------------------- #
# 广场相关辅助函数
# --------------------------------------------------------------------------- #


def _author_score(rating: str | None) -> float | None:
    """把作者三档评分映射为 0/5/8。"""
    mapping = {"bad": 0.0, "ok": 5.0, "top": 8.0}
    return mapping.get(rating) if rating else None


def _author_score_10(rating: str | None) -> float:
    """把作者三档评分映射为 0-10 制：bad=0, ok=6.25, top=10。"""
    mapping = {"bad": 0.0, "ok": 6.25, "top": 10.0}
    return mapping.get(rating, 0.0) if rating else 0.0


def _get_nickname(session: Session, user_id: str) -> str | None:
    """获取用户昵称。"""
    user = session.query(UserProfile).filter_by(user_id=user_id).first()
    return user.nickname if user else None


def _aggregate_square_fields(session: Session, result_id: str) -> dict[str, Any]:
    """汇总一个广场段子的路人评分与评论数。"""
    avg_score = (
        session.query(func.avg(JokeRating.score))
        .filter_by(result_id=result_id)
        .scalar()
    )
    rating_count = (
        session.query(func.count(JokeRating.rating_id))
        .filter_by(result_id=result_id)
        .scalar()
    )
    comment_count = (
        session.query(func.count(JokeComment.comment_id))
        .filter_by(result_id=result_id)
        .scalar()
    )
    return {
        "average_score": round(avg_score, 2) if avg_score is not None else None,
        "rating_count": rating_count or 0,
        "comment_count": comment_count or 0,
    }


# --------------------------------------------------------------------------- #
# 发布/取消发布接口
# --------------------------------------------------------------------------- #


@router.post("/results/{result_id}/publish", response_model=PublishResponse)
async def publish_eval_result(
    result_id: str,
    user_id: str = Depends(get_current_user),
) -> PublishResponse:
    """把评测结果发布到广场（仅作者可操作）。"""
    with _db_session() as session:
        result = (
            session.query(EvalResult)
            .join(EvalSession)
            .filter(EvalResult.result_id == result_id, EvalSession.user_id == user_id)
            .first()
        )
        if result is None:
            raise HTTPException(status_code=404, detail="结果不存在")
        if result.status != "done":
            raise HTTPException(status_code=400, detail="只能发布已生成完成的段子")
        if result.is_published:
            raise HTTPException(status_code=400, detail="该段子已经发布")

        result.is_published = True
        result.published_at = datetime.utcnow()
        session.commit()

    return PublishResponse(success=True)


@router.delete("/results/{result_id}/publish", response_model=PublishResponse)
async def unpublish_eval_result(
    result_id: str,
    user_id: str = Depends(get_current_user),
) -> PublishResponse:
    """取消发布广场段子（仅作者可操作）。"""
    with _db_session() as session:
        result = (
            session.query(EvalResult)
            .join(EvalSession)
            .filter(EvalResult.result_id == result_id, EvalSession.user_id == user_id)
            .first()
        )
        if result is None:
            raise HTTPException(status_code=404, detail="结果不存在")
        if not result.is_published:
            raise HTTPException(status_code=400, detail="该段子未发布")

        result.is_published = False
        result.published_at = None
        session.commit()

    return PublishResponse(success=True)


# --------------------------------------------------------------------------- #
# 广场列表/详情接口
# --------------------------------------------------------------------------- #


@router.get("/square", response_model=SquareListResponse)
async def list_square_jokes(
    user_id: str = Depends(get_current_user),
    sort: str = "newest",
    page: int = 1,
    page_size: int = 20,
) -> SquareListResponse:
    """获取广场已发布段子列表。"""
    if sort not in ("newest", "hottest"):
        raise HTTPException(status_code=400, detail="sort 必须是 newest 或 hottest")
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    with _db_session() as session:
        base_query = (
            session.query(EvalResult, EvalSession, UserProfile)
            .join(EvalSession, EvalResult.session_id == EvalSession.session_id)
            .join(UserProfile, EvalSession.user_id == UserProfile.user_id)
            .filter(EvalResult.is_published == True)  # noqa: E712
        )

        if sort == "newest":
            base_query = base_query.order_by(EvalResult.published_at.desc())

        total = base_query.count()
        rows = base_query.offset((page - 1) * page_size).limit(page_size).all()

        jokes: list[SquareJokeItem] = []
        for result, eval_session, author in rows:
            agg = _aggregate_square_fields(session, result.result_id)
            author_rating = result.rating
            author_score = _author_score(author_rating)
            author_score_10 = _author_score_10(author_rating)
            avg_public = agg["average_score"] or author_score_10
            hot_score = (avg_public + author_score_10) / 2 * 10 + agg["comment_count"] * 2

            jokes.append(
                SquareJokeItem(
                    result_id=result.result_id,
                    author_id=author.user_id,
                    author_nickname=author.nickname,
                    section_title=result.section_title,
                    content=result.content or "",
                    model=result.model,
                    author_rating=author_rating,
                    author_score=author_score,
                    average_score=agg["average_score"],
                    rating_count=agg["rating_count"],
                    comment_count=agg["comment_count"],
                    published_at=result.published_at.isoformat()
                    if result.published_at
                    else "",
                    hot_score=round(hot_score, 2),
                )
            )

        if sort == "hottest":
            jokes.sort(key=lambda x: x.hot_score, reverse=True)

        return SquareListResponse(
            jokes=jokes,
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/square/{result_id}", response_model=SquareJokeDetail)
async def get_square_joke_detail(
    result_id: str,
    user_id: str = Depends(get_current_user),
) -> SquareJokeDetail:
    """获取广场段子详情。"""
    with _db_session() as session:
        row = (
            session.query(EvalResult, EvalSession, UserProfile)
            .join(EvalSession, EvalResult.session_id == EvalSession.session_id)
            .join(UserProfile, EvalSession.user_id == UserProfile.user_id)
            .filter(
                EvalResult.result_id == result_id,
                EvalResult.is_published == True,  # noqa: E712
            )
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="段子不存在或未发布")

        result, eval_session, author = row
        agg = _aggregate_square_fields(session, result_id)
        my_rating = (
            session.query(JokeRating).filter_by(result_id=result_id, user_id=user_id).first()
        )

        return SquareJokeDetail(
            result_id=result.result_id,
            author_id=author.user_id,
            author_nickname=author.nickname,
            section_title=result.section_title,
            content=result.content or "",
            model=result.model,
            inputs={
                "topic": eval_session.topic,
                "attitude": eval_session.attitude,
                "bias": eval_session.bias,
                "emotion": eval_session.emotion,
                "duration": eval_session.duration,
            },
            author_rating=result.rating,
            author_score=_author_score(result.rating),
            average_score=agg["average_score"],
            rating_count=agg["rating_count"],
            comment_count=agg["comment_count"],
            my_score=my_rating.score if my_rating else None,
            published_at=result.published_at.isoformat() if result.published_at else "",
        )


# --------------------------------------------------------------------------- #
# 路人评分/点评接口
# --------------------------------------------------------------------------- #


@router.post("/square/{result_id}/rate", response_model=PublicRateResponse)
async def rate_square_joke(
    result_id: str,
    request: PublicRateRequest,
    user_id: str = Depends(get_current_user),
) -> PublicRateResponse:
    """对广场段子进行路人评分（0-10）。"""
    with _db_session() as session:
        result = (
            session.query(EvalResult)
            .filter_by(result_id=result_id, is_published=True)
            .first()
        )
        if result is None:
            raise HTTPException(status_code=404, detail="段子不存在或未发布")

        # 检查是否是作者自己
        eval_session = (
            session.query(EvalSession)
            .filter_by(session_id=result.session_id, user_id=user_id)
            .first()
        )
        if eval_session is not None:
            raise HTTPException(status_code=400, detail="不能给自己的段子打分")

        rating = session.query(JokeRating).filter_by(
            result_id=result_id, user_id=user_id
        ).first()
        if rating is None:
            rating = JokeRating(
                rating_id=uuid.uuid4().hex[:16],
                result_id=result_id,
                user_id=user_id,
                score=request.score,
            )
            session.add(rating)
        else:
            rating.score = request.score
            rating.updated_at = datetime.utcnow()
        session.commit()

        agg = _aggregate_square_fields(session, result_id)
        return PublicRateResponse(
            success=True,
            average_score=agg["average_score"],
            rating_count=agg["rating_count"],
        )


@router.post("/square/{result_id}/comments", response_model=CommentItem)
async def post_square_comment(
    result_id: str,
    request: CommentRequest,
    user_id: str = Depends(get_current_user),
) -> CommentItem:
    """对广场段子发表评论。"""
    with _db_session() as session:
        result = (
            session.query(EvalResult)
            .filter_by(result_id=result_id, is_published=True)
            .first()
        )
        if result is None:
            raise HTTPException(status_code=404, detail="段子不存在或未发布")

        comment = JokeComment(
            comment_id=uuid.uuid4().hex[:16],
            result_id=result_id,
            user_id=user_id,
            content=request.content.strip(),
        )
        session.add(comment)
        session.commit()

        nickname = _get_nickname(session, user_id)
        return CommentItem(
            comment_id=comment.comment_id,
            user_id=user_id,
            nickname=nickname,
            content=comment.content,
            created_at=comment.created_at.isoformat() if comment.created_at else "",
        )


@router.get("/square/{result_id}/comments", response_model=CommentListResponse)
async def list_square_comments(
    result_id: str,
    page: int = 1,
    page_size: int = 20,
) -> CommentListResponse:
    """获取广场段子的点评列表（公开，无需登录也可调用）。"""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    with _db_session() as session:
        result = (
            session.query(EvalResult)
            .filter_by(result_id=result_id, is_published=True)
            .first()
        )
        if result is None:
            raise HTTPException(status_code=404, detail="段子不存在或未发布")

        total = session.query(JokeComment).filter_by(result_id=result_id).count()
        comments = (
            session.query(JokeComment, UserProfile)
            .join(UserProfile, JokeComment.user_id == UserProfile.user_id)
            .filter(JokeComment.result_id == result_id)
            .order_by(JokeComment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return CommentListResponse(
            comments=[
                CommentItem(
                    comment_id=c.comment_id,
                    user_id=c.user_id,
                    nickname=u.nickname,
                    content=c.content,
                    created_at=c.created_at.isoformat() if c.created_at else "",
                )
                for c, u in comments
            ],
            total=total,
        )


# --------------------------------------------------------------------------- #
# 后台生成任务
# --------------------------------------------------------------------------- #


def _run_eval_generation(
    session_id: str,
    user_id: str,
    skill_name: str,
    model: str,
    topic: str,
    attitude: str,
    bias: str,
    emotion: str,
    duration: int,
) -> None:
    """后台执行生成任务：直接调用指定 Skill 生成完整段子。"""
    try:
        with _db_session() as session:
            result = (
                session.query(EvalResult)
                .filter_by(session_id=session_id, section_id="full")
                .first()
            )
            if result is None:
                return
            result.status = "running"
            session.commit()

        # 优先使用 orchestrator 中已注册的 Skill（已注入 retriever/memory）
        skill = None
        if state.orch is not None:
            for tool in getattr(state.orch, "tools", []) or []:
                if getattr(tool, "name", None) == skill_name:
                    skill = tool
                    break

        if skill is None:
            skill = load_single_skill(Path(settings.skills_dir) / skill_name)

        if skill is None:
            raise ValueError(f"Skill '{skill_name}' 不存在")

        if model:
            skill.model_name = model

        content = skill.invoke(
            {
                "topic": topic,
                "attitude": attitude,
                "bias": bias or "无",
                "emotion": emotion,
                "duration": duration,
                "user_id": user_id,
                "debug": False,
            }
        )

        with _db_session() as session:
            result = (
                session.query(EvalResult)
                .filter_by(session_id=session_id, section_id="full")
                .first()
            )
            if result is not None:
                result.content = content
                result.status = "done"
                result.completed_at = datetime.utcnow()
                session.commit()

            eval_session = (
                session.query(EvalSession)
                .filter_by(session_id=session_id, user_id=user_id)
                .first()
            )
            if eval_session is not None:
                eval_session.status = "done"
                eval_session.updated_at = datetime.utcnow()
                session.commit()

    except Exception as exc:  # noqa: BLE001
        logger.exception("评测会话 %s 生成失败", session_id)
        with _db_session() as session:
            result = (
                session.query(EvalResult)
                .filter_by(session_id=session_id, section_id="full")
                .first()
            )
            if result is not None:
                result.status = "failed"
                result.error = f"{type(exc).__name__}: {exc}"
                result.completed_at = datetime.utcnow()
                session.commit()

            eval_session = (
                session.query(EvalSession)
                .filter_by(session_id=session_id, user_id=user_id)
                .first()
            )
            if eval_session is not None:
                eval_session.status = "failed"
                eval_session.updated_at = datetime.utcnow()
                session.commit()
