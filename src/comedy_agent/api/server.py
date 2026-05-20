"""FastAPI HTTP 服务入口。

提供 RESTful API 供内部调试与前端对接。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.agent.orchestrator import AgentOrchestrator
from comedy_agent.api.middleware import RateLimitMiddleware
from comedy_agent.core.config import settings
from comedy_agent.core.rate_limiter import get_rate_limiter
from comedy_agent.memory.models import ScriptData
from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.models.factory import ModelConfigError
from comedy_agent.rag.feedback_loop import FeedbackLoop
from comedy_agent.skills import (
    CrosstalkSkill,
    JokeAnalyzerSkill,
    ScriptEvaluatorSkill,
    SitcomSkill,
    SketchSkill,
    StandupSkill,
)
from comedy_agent.skills.loader import load_plugin_skills
from comedy_agent.core.prompt_manager import PromptManager


# ------------------------------------------------------------------ #
# 请求/响应模型
# ------------------------------------------------------------------ #
class ChatRequest(BaseModel):
    """聊天请求。"""

    prompt: str = Field(description="用户输入")
    model: str | None = Field(default=None, description="指定模型")
    user_id: str | None = Field(default=None, description="用户标识，用于注入记忆上下文")
    chat_history: list[tuple[str, str]] | None = Field(
        default=None, description="历史消息 [(role, content), ...]"
    )


class ChatResponse(BaseModel):
    """聊天响应。"""

    output: str = Field(description="Agent 输出文本")
    messages: list[dict[str, Any]] = Field(
        default_factory=list, description="完整消息链"
    )


class SkillListResponse(BaseModel):
    """Skill 列表响应。"""

    skills: list[str] = Field(description="已注册 Skill 名称列表")


class StandupRequest(BaseModel):
    """脱口秀创作请求。"""

    topic: str = Field(description="主题")
    style: str = Field(default="日常观察", description="风格")
    duration: int = Field(default=3, description="时长（分钟）")
    audience: str = Field(default="通用", description="受众")


class StandupResponse(BaseModel):
    """脱口秀创作响应。"""

    content: str = Field(description="生成的段子")


# ------------------------------------------------------------------ #
# 作品管理请求/响应模型
# ------------------------------------------------------------------ #
class ScriptCreateRequest(BaseModel):
    """创建作品请求。"""

    user_id: str = Field(description="用户标识")
    title: str | None = Field(default=None, description="作品标题")
    content: str = Field(description="作品内容")
    script_type: str | None = Field(
        default=None, description="作品类型：standup / sketch / crosstalk / sitcom"
    )
    tags: list[str] | None = Field(default=None, description="标签列表")
    rating: float | None = Field(default=None, description="评分 0.0-5.0")


class ScriptUpdateRequest(BaseModel):
    """更新作品请求。"""

    user_id: str = Field(description="用户标识")
    title: str | None = Field(default=None, description="作品标题")
    content: str | None = Field(default=None, description="作品内容")
    script_type: str | None = Field(default=None, description="作品类型")
    tags: list[str] | None = Field(default=None, description="标签列表")
    rating: float | None = Field(default=None, description="评分 0.0-5.0")


class ScriptRateRequest(BaseModel):
    """作品评分请求。"""

    rating: float = Field(description="评分 0.0-5.0")


class ScriptListResponse(BaseModel):
    """作品列表响应。"""

    scripts: list[ScriptData] = Field(description="作品列表")


class ScriptDetailResponse(BaseModel):
    """作品详情响应。"""

    script: ScriptData | None = Field(default=None, description="作品详情")


class SuccessResponse(BaseModel):
    """通用成功响应。"""

    success: bool = Field(description="是否成功")


class FeedbackIngestRequest(BaseModel):
    """高评分内容回流请求。"""

    user_id: str | None = Field(default=None, description="用户标识，为空时处理所有用户")
    min_rating: float | None = Field(default=None, description="最低评分阈值，默认 4.0")
    chunk_strategy: str | None = Field(
        default=None, description="分块策略：fixed / paragraph / scene / dialogue"
    )
    dry_run: bool = Field(default=False, description="为 True 时只统计不实际入库")


class FeedbackIngestResponse(BaseModel):
    """高评分内容回流响应。"""

    ingested_scripts: int = Field(description="实际回流作品数")
    total_chunks: int = Field(description="总分块数")
    script_ids: list[str] = Field(description="回流作品 ID 列表")
    skipped: list[str] = Field(description="已入库被跳过的作品 ID 列表")
    dry_run: bool = Field(description="是否为模拟运行")


# ------------------------------------------------------------------ #
# 应用生命周期
# ------------------------------------------------------------------ #
class AppState:
    """全局应用状态（持有 Orchestrator 与 Memory 实例）。"""

    def __init__(self) -> None:
        self.orch: AgentOrchestrator | None = None
        self.memory: UnifiedMemory | None = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载 Prompt、Memory 与初始化 Orchestrator。"""
    # 加载外部 Prompt 模板
    PromptManager().load_from_directory()

    # 初始化统一记忆
    try:
        state.memory = UnifiedMemory()
    except Exception as e:
        import logging

        logging.getLogger("comedy-agent").warning("记忆系统初始化失败: %s", e)
        state.memory = None

    try:
        state.orch = AgentOrchestrator(memory=state.memory)
        state.orch.register_skill(StandupSkill())
        state.orch.register_skill(CrosstalkSkill())
        state.orch.register_skill(SketchSkill())
        state.orch.register_skill(SitcomSkill())
        state.orch.register_skill(JokeAnalyzerSkill())
        state.orch.register_skill(ScriptEvaluatorSkill())

        # 加载外部插件 Skill
        for plugin in load_plugin_skills():
            state.orch.register_skill(plugin)
    except ModelConfigError as e:
        import logging

        logging.getLogger("comedy-agent").error("模型配置错误: %s", e)
        state.orch = None
    yield
    state.orch = None
    state.memory = None


app = FastAPI(
    title="Comedy Agent API",
    description="喜剧行业垂直 Agent HTTP 接口",
    version="0.1.0",
    lifespan=lifespan,
)

# 注册限流中间件（Redis 优先，失败降级到内存）
limiter = get_rate_limiter()
app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter,
    write_max=settings.rate_limit_write_max,
    write_window=settings.rate_limit_write_window,
    read_max=settings.rate_limit_read_max,
    read_window=settings.rate_limit_read_window,
)


# ------------------------------------------------------------------ #
# 路由
# ------------------------------------------------------------------ #
@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """健康检查。"""
    return {"status": "ok"}


@app.get("/skills", response_model=SkillListResponse, tags=["skills"])
async def list_skills() -> SkillListResponse:
    """列出所有已注册 Skill。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    return SkillListResponse(skills=state.orch.list_skills())


@app.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(request: ChatRequest) -> ChatResponse:
    """与 Agent 对话。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")

    try:
        result = state.orch.run(
            request.prompt,
            chat_history=request.chat_history,
            user_id=request.user_id,
        )
        # 将消息对象序列化为 dict
        messages = []
        for msg in result.get("messages", []):
            messages.append(
                {
                    "type": getattr(msg, "type", "unknown"),
                    "content": getattr(msg, "content", ""),
                }
            )
        return ChatResponse(output=result["output"], messages=messages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/skills/standup", response_model=StandupResponse, tags=["skills"])
async def skill_standup(request: StandupRequest) -> StandupResponse:
    """直接调用脱口秀创作 Skill。"""
    skill = StandupSkill()
    try:
        content = skill.invoke(
            {
                "topic": request.topic,
                "style": request.style,
                "duration": request.duration,
                "audience": request.audience,
            }
        )
        return StandupResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------ #
# 作品管理路由
# ------------------------------------------------------------------ #
@app.post("/scripts", response_model=ScriptData, tags=["scripts"])
async def create_script(request: ScriptCreateRequest) -> ScriptData:
    """保存（创建）新作品。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    script = ScriptData(
        title=request.title,
        content=request.content,
        script_type=request.script_type,
        tags=request.tags,
        rating=request.rating,
    )
    return state.memory.save_script(request.user_id, script)


@app.get("/scripts", response_model=ScriptListResponse, tags=["scripts"])
async def list_scripts(
    user_id: str, script_type: str | None = None
) -> ScriptListResponse:
    """列出用户的作品。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    scripts = state.memory.list_scripts(user_id, script_type)
    return ScriptListResponse(scripts=scripts)


@app.get("/scripts/{script_id}", response_model=ScriptDetailResponse, tags=["scripts"])
async def get_script(script_id: str) -> ScriptDetailResponse:
    """获取单个作品详情。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    script = state.memory.load_script(script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    return ScriptDetailResponse(script=script)


@app.put("/scripts/{script_id}", response_model=ScriptData, tags=["scripts"])
async def update_script(script_id: str, request: ScriptUpdateRequest) -> ScriptData:
    """更新作品。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    existing = state.memory.load_script(script_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    updated = ScriptData(
        script_id=script_id,
        title=request.title if request.title is not None else existing.title,
        content=request.content if request.content is not None else existing.content,
        script_type=request.script_type
        if request.script_type is not None
        else existing.script_type,
        tags=request.tags if request.tags is not None else existing.tags,
        rating=request.rating if request.rating is not None else existing.rating,
    )
    return state.memory.save_script(request.user_id, updated)


@app.delete("/scripts/{script_id}", response_model=SuccessResponse, tags=["scripts"])
async def delete_script(script_id: str) -> SuccessResponse:
    """删除作品。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    ok = state.memory.delete_script(script_id)
    if not ok:
        raise HTTPException(status_code=404, detail="作品不存在")
    return SuccessResponse(success=True)


@app.patch("/scripts/{script_id}/rate", response_model=SuccessResponse, tags=["scripts"])
async def rate_script(script_id: str, request: ScriptRateRequest) -> SuccessResponse:
    """为作品评分。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    ok = state.memory.rate_script(script_id, request.rating)
    if not ok:
        raise HTTPException(status_code=404, detail="作品不存在")
    return SuccessResponse(success=True)


# ------------------------------------------------------------------ #
# 高评分内容回流路由
# ------------------------------------------------------------------ #
@app.post("/feedback/ingest", response_model=FeedbackIngestResponse, tags=["feedback"])
async def feedback_ingest(request: FeedbackIngestRequest) -> FeedbackIngestResponse:
    """将用户高评分剧本回流到知识库，实现持续进化。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    try:
        loop = FeedbackLoop(
            memory=state.memory,
            min_rating=request.min_rating if request.min_rating is not None else 4.0,
        )
        result = loop.ingest_high_rated_scripts(
            user_id=request.user_id,
            chunk_strategy=request.chunk_strategy or "paragraph",
            dry_run=request.dry_run,
        )
        return FeedbackIngestResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
