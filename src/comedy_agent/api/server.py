"""FastAPI HTTP 服务入口。

提供 RESTful API 供内部调试与前端对接。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from comedy_agent.agent.orchestrator import AgentOrchestrator
from comedy_agent.api.middleware import RateLimitMiddleware
from comedy_agent.api.state import state
from comedy_agent.api.routers.actor import router as actor_router
from comedy_agent.api.routers.admin import router as admin_router
from comedy_agent.api.routers.export import router as export_router
from comedy_agent.api.routers.ip_styles import router as ip_styles_router
from comedy_agent.api.routers.projects import router as projects_router
from comedy_agent.api.routers.salt import router as salt_router
from comedy_agent.api.routers.submissions import router as submissions_router
from comedy_agent.api.routers.wallet import router as wallet_router
from comedy_agent.auth import get_current_user, router as auth_router
from comedy_agent.core.config import settings
from comedy_agent.core.observability import get_metrics, get_tracer, reset_observability, setup_langsmith
from comedy_agent.evaluation.model_quality import ModelOutputEvaluator
from comedy_agent.evaluation.script_quality import ScriptQualityEvaluator
from comedy_agent.core.rate_limiter import get_rate_limiter
from comedy_agent.memory.models import DocumentData, ScriptData
from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.models.factory import ModelConfigError, ModelFactory
from comedy_agent.rag.feedback_loop import FeedbackLoop
from comedy_agent.rag.ingest import KnowledgeIngestor
from comedy_agent.rag.retriever import ComedyRetriever
from comedy_agent.rag.vector_store import VectorStore
from comedy_agent.skills import (
    AddSaltSkill,
    CrosstalkSkill,
    JapaneseSketchSkill,
    JokeAnalyzerSkill,
    ManzaiSkill,
    ScriptEvaluatorSkill,
    SitcomSkill,
    SketchSkill,
    StandupSkill,
)
from comedy_agent.skills.loader import load_plugin_skills
from comedy_agent.core.prompt_manager import PromptManager
from comedy_agent.models.factory import ModelFactory

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# 请求/响应模型
# ------------------------------------------------------------------ #
class ChatRequest(BaseModel):
    """聊天请求。"""

    prompt: str = Field(description="用户输入")
    model: str | None = Field(default=None, description="指定模型")
    session_id: str | None = Field(default=None, description="会话标识，为空则新建会话")
    chat_history: list[tuple[str, str]] | None = Field(
        default=None, description="历史消息 [(role, content), ...]"
    )


class SuggestionResponse(BaseModel):
    """改进建议响应。"""

    skill_name: str | None = Field(default=None, description="Skill 标识名")
    skill_type: str | None = Field(default=None, description="Skill 类型")
    topic: str | None = Field(default=None, description="创作主题")
    current_style: str | None = Field(default=None, description="当前风格")
    available_styles: list[str] = Field(default_factory=list, description="可用风格列表")
    prompt_template: str | None = Field(default=None, description="前端构造改进请求的模板")


class ChatResponse(BaseModel):
    """聊天响应。"""

    output: str = Field(description="Agent 输出文本")
    session_id: str | None = Field(default=None, description="会话标识")
    model: str | None = Field(default=None, description="使用的模型")
    messages: list[dict[str, Any]] = Field(
        default_factory=list, description="完整消息链"
    )
    suggestion: SuggestionResponse | None = Field(default=None, description="改进建议")


class SkillListResponse(BaseModel):
    """Skill 列表响应。"""

    skills: list[dict[str, Any]] = Field(description="已注册 Skill 详细信息列表")


class SkillInstallRequest(BaseModel):
    """安装 Skill 请求。"""

    name: str = Field(description="Skill 名称标识（只允许字母/数字/下划线/连字符）")
    skill_md: str = Field(description="SKILL.md 文件内容")
    prompt_txt: str = Field(description="prompt.txt 文件内容")
    skill_py: str | None = Field(default=None, description="可选的 skill.py 代码内容")


class SkillReloadResponse(BaseModel):
    """热重载响应。"""

    added: int = Field(description="新增 Skill 数量")
    removed: int = Field(description="移除 Skill 数量")
    unchanged: int = Field(description="未变更 Skill 数量")


class StandupRequest(BaseModel):
    """脱口秀创作请求。"""

    topic: str = Field(description="主题")
    style: str = Field(default="日常观察", description="风格")
    duration: int = Field(default=3, description="时长（分钟）")
    audience: str = Field(default="通用", description="受众")
    density: str = Field(default="标准", description="笑点密度：密集/标准/稀疏")
    perspective_count: int = Field(default=2, description="多视角版本数量（2-3）")
    model: str | None = Field(default=None, description="指定模型")
    debug: bool = Field(default=False, description="Debug 模式：True 时输出分析过程，False 时只输出正文")


class StandupResponse(BaseModel):
    """脱口秀创作响应。"""

    content: str = Field(description="生成的段子")


class SketchRequest(BaseModel):
    """小品创作请求。"""

    theme: str = Field(description="主题")
    style: str = Field(default="现代小品", description="风格：传统小品/现代小品/荒诞小品/温情小品")
    characters_count: int = Field(default=3, description="角色数量（2-5人）")
    setting: str = Field(default="家庭", description="场景设定")
    duration: int = Field(default=8, description="时长（分钟）")
    conflict_type: str = Field(default="执念vs现实", description="冲突类型：执念vs现实/执念vs执念/信息差")
    model: str | None = Field(default=None, description="指定模型")


class SketchResponse(BaseModel):
    """小品创作响应。"""

    content: str = Field(description="生成的剧本")


class ManzaiRequest(BaseModel):
    """漫才创作请求。"""

    topic: str = Field(description="话题")
    style: str = Field(default="传统漫才", description="风格：传统漫才/快节奏漫才/温情漫才/怪诞漫才")
    duration: int = Field(default=5, description="时长（分钟）")
    segments_count: int = Field(default=3, description="段落数量")
    absurd_level: str = Field(default="标准", description="荒谬等级：轻微/标准/极致")
    model: str | None = Field(default=None, description="指定模型")


class ManzaiResponse(BaseModel):
    """漫才创作响应。"""

    content: str = Field(description="生成的对白")


class JapaneseSketchRequest(BaseModel):
    """日式短剧创作请求。"""

    theme: str = Field(description="主题")
    style: str = Field(default="经典コント", description="风格：经典コント/黑色幽默/温情喜剧/荒诞喜剧")
    characters_count: int = Field(default=2, description="角色数量（2-3人）")
    setting: str = Field(default="便利店", description="场景设定")
    duration: int = Field(default=5, description="时长（分钟）")
    character_type: str = Field(default="偏执", description="极端性格：偏执/懦弱/自大/较真")
    punchline_density: int = Field(default=4, description="笑点密度（个/分钟）")
    model: str | None = Field(default=None, description="指定模型")


class JapaneseSketchResponse(BaseModel):
    """日式短剧创作响应。"""

    content: str = Field(description="生成的剧本")


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
# 文档管理请求/响应模型
# ------------------------------------------------------------------ #
class DocumentUploadResponse(BaseModel):
    """文档上传响应。"""

    doc_id: str = Field(description="文档标识")
    filename: str = Field(description="文件名")
    kind: str | None = Field(default=None, description="喜剧种类")
    style: str | None = Field(default=None, description="风格标识")
    chunk_strategy: str | None = Field(default=None, description="分块策略")
    topic: str | None = Field(default=None, description="文档主题")
    status: str = Field(description="处理状态")
    chunks: int = Field(description="分块数量")


class DocumentListResponse(BaseModel):
    """文档列表响应。"""

    documents: list[DocumentData] = Field(description="文档列表")


# ------------------------------------------------------------------ #
# 学习模式请求/响应模型
# ------------------------------------------------------------------ #
class LearnChatRequest(BaseModel):
    """学习模式对话请求。"""

    query: str = Field(description="学习问题")
    doc_ids: list[str] | None = Field(default=None, description="指定文档 ID 列表，为空则检索全部个人知识库")
    mode: str = Field(default="explain", description="分析模式：explain / analyze / extract")


class LearnChatResponse(BaseModel):
    """学习模式对话响应。"""

    output: str = Field(description="AI 分析回答")
    references: list[dict[str, Any]] = Field(default_factory=list, description="引用的参考资料")


# ------------------------------------------------------------------ #
# 技巧库请求/响应模型
# ------------------------------------------------------------------ #
class KnowledgeCardData(BaseModel):
    """技巧卡片数据。"""

    card_id: str | None = Field(default=None, description="卡片唯一标识")
    user_id: str = Field(description="所属用户")
    title: str = Field(description="技巧名称")
    content: str = Field(description="技巧内容/说明")
    card_type: str = Field(default="technique", description="卡片类型：technique / concept / formula / pattern")
    tags: list[str] | None = Field(default=None, description="标签列表")
    source_doc_id: str | None = Field(default=None, description="来源文档 ID")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class KnowledgeCardListResponse(BaseModel):
    """技巧卡片列表响应。"""

    cards: list[KnowledgeCardData] = Field(description="卡片列表")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载 Prompt、Memory、可观测性与初始化 Orchestrator。"""
    import time

    state.start_time = time.time()

    # 自动配置 LangSmith（若配置了 API Key）
    setup_langsmith()

    # 加载外部 Prompt 模板
    PromptManager().load_from_directory()

    # 初始化统一记忆
    try:
        state.memory = UnifiedMemory()
    except Exception as e:
        import logging

        logging.getLogger("comedy-agent").warning("记忆系统初始化失败: %s", e)
        state.memory = None

    # 初始化知识库检索器
    retriever: ComedyRetriever | None = None
    try:
        vector_store = VectorStore(
            collection_name="comedy_knowledge",
            persist_path=str(settings.vector_db_path),
        )
        retriever = ComedyRetriever(vector_store=vector_store)
        import logging
        logging.getLogger("comedy-agent").info("知识库检索器已初始化")
    except Exception as e:
        import logging
        logging.getLogger("comedy-agent").warning("知识库检索器初始化失败: %s", e)
        retriever = None

    try:
        state.orch = AgentOrchestrator(memory=state.memory, retriever=retriever)
        state.orch.register_skill(StandupSkill())
        state.orch.register_skill(CrosstalkSkill())
        state.orch.register_skill(SketchSkill())
        state.orch.register_skill(SitcomSkill())
        state.orch.register_skill(ManzaiSkill())
        state.orch.register_skill(JapaneseSketchSkill())
        state.orch.register_skill(JokeAnalyzerSkill())
        state.orch.register_skill(ScriptEvaluatorSkill())
        state.orch.register_skill(AddSaltSkill())

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
    reset_observability()


app = FastAPI(
    title="Comedy Agent API",
    description="喜剧行业垂直 Agent HTTP 接口",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 跨域支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载认证路由
app.include_router(auth_router, prefix="/auth")
app.include_router(wallet_router)
app.include_router(projects_router)
app.include_router(salt_router)
app.include_router(ip_styles_router)
app.include_router(submissions_router)
app.include_router(actor_router)
app.include_router(admin_router)
app.include_router(export_router)

# 挂载前端静态文件（如果 frontend/ 目录存在）
_frontend_dir = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_frontend_dir)), name="static")


@app.get("/")
async def root() -> FileResponse:
    """返回首页。"""
    index_path = _frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    raise HTTPException(status_code=404, detail="首页不存在")


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
# 健康检查
# ------------------------------------------------------------------ #
class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str
    version: str
    memory_ready: bool
    orchestrator_ready: bool
    uptime_seconds: float | None = None


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """健康检查 —— 返回各子系统就绪状态。"""
    import time

    return HealthResponse(
        status="ok",
        version="0.1.0",
        memory_ready=state.memory is not None,
        orchestrator_ready=state.orch is not None,
        uptime_seconds=time.time() - state.start_time if state.start_time else None,
    )


# ------------------------------------------------------------------ #
# 路由
# ------------------------------------------------------------------ #


@app.get("/skills", response_model=SkillListResponse, tags=["skills"])
async def list_skills() -> SkillListResponse:
    """列出所有已注册 Skill。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    return SkillListResponse(skills=state.orch.list_skills())


@app.post("/skills/install", response_model=SkillListResponse, tags=["skills"])
async def install_skill(
    request: SkillInstallRequest,
    user_id: str = Depends(get_current_user),
) -> SkillListResponse:
    """安装新 Skill（声明式或代码式）。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")

    from comedy_agent.skills.loader import (
        is_builtin_skill,
        load_single_skill,
        validate_skill_name,
        validate_skill_py,
    )

    name = request.name.strip()
    if not validate_skill_name(name):
        raise HTTPException(status_code=400, detail="Skill 名称不合法，只允许字母、数字、下划线和连字符")
    if is_builtin_skill(name):
        raise HTTPException(status_code=400, detail=f"'{name}' 是内置 Skill，禁止覆盖")

    # 校验 skill_py 语法
    if request.skill_py:
        if not validate_skill_py(request.skill_py):
            raise HTTPException(status_code=400, detail="skill.py 代码语法错误")

    # 写入 skills/ 目录
    skills_dir = Path(settings.skills_dir)
    skill_dir = skills_dir / name
    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(request.skill_md, encoding="utf-8")
        (skill_dir / "prompt.txt").write_text(request.prompt_txt, encoding="utf-8")
        if request.skill_py:
            (skill_dir / "skill.py").write_text(request.skill_py, encoding="utf-8")
    except Exception as e:
        logger.error("写入 Skill 文件失败: %s", e)
        raise HTTPException(status_code=500, detail="写入 Skill 文件失败")

    # 加载并注册
    skill = load_single_skill(skill_dir)
    if skill is None:
        raise HTTPException(status_code=500, detail="Skill 加载失败，请检查 SKILL.md 格式")

    state.orch.register_skill(skill)
    return SkillListResponse(skills=state.orch.list_skills())


@app.delete("/skills/{name}", response_model=dict[str, Any], tags=["skills"])
async def uninstall_skill(
    name: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """卸载插件 Skill。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")

    from comedy_agent.skills.loader import is_builtin_skill

    if is_builtin_skill(name):
        raise HTTPException(status_code=400, detail=f"'{name}' 是内置 Skill，禁止卸载")

    # 注销 Skill
    if not state.orch.unregister_skill(name):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 未找到")

    # 删除目录
    skill_dir = Path(settings.skills_dir) / name
    if skill_dir.exists():
        import shutil
        shutil.rmtree(skill_dir)

    return {"success": True, "name": name}


@app.post("/skills/reload", response_model=SkillReloadResponse, tags=["skills"])
async def reload_skills(
    user_id: str = Depends(get_current_user),
) -> SkillReloadResponse:
    """热重载所有插件 Skill。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    stats = state.orch.reload_plugins()
    return SkillReloadResponse(**stats)


CHAT_COST = 5

@app.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(
    request: ChatRequest, user_id: str = Depends(get_current_user)
) -> ChatResponse:
    """与 Agent 对话。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    if state.memory is not None:
        account = state.memory.get_token_account(user_id)
        if account.balance < CHAT_COST:
            raise HTTPException(status_code=402, detail=f"Token 余额不足（需 {CHAT_COST}，余 {account.balance}）")

    tracer = get_tracer()
    metrics = get_metrics()

    try:
        # 若前端指定了模型，运行时切换
        if request.model:
            state.orch.set_model(request.model)

        # 生成或复用 session_id
        import uuid
        session_id = request.session_id or uuid.uuid4().hex[:16]

        with tracer.span(
            "api.chat",
            input_data={"prompt": request.prompt[:200], "user_id": user_id},
            metadata={"model": request.model, "endpoint": "/chat", "session_id": session_id},
        ) as span:
            result = state.orch.run(
                request.prompt,
                chat_history=request.chat_history,
                user_id=user_id,
            )
            # 将消息对象序列化为 dict
            messages = []
            for msg in result.get("messages", []):
                messages.append(
                    {
                        "role": getattr(msg, "type", "unknown"),
                        "content": str(getattr(msg, "content", "")),
                    }
                )

            # 保存会话记录到数据库
            if state.memory is not None:
                try:
                    state.memory.save_conversation(
                        user_id=user_id,
                        session_id=session_id,
                        messages=messages,
                        summary=result["output"][:80] if result["output"] else None,
                    )
                except Exception as save_err:
                    logger.warning("保存会话记录失败: %s", save_err)

            span.output_data = {"output": result["output"][:200]}
            metrics.record("api.chat.duration_ms", span.duration_ms)
            orch_model = getattr(state.orch, 'model_name', None) if state.orch else None
            model_used = request.model or (orch_model if isinstance(orch_model, str) else None) or settings.default_model

            # 构造改进建议（仅创作类 Skill）
            skill_meta = result.get("skill_meta")
            suggestion = None
            if skill_meta and skill_meta.get("skill_type") == "creative":
                skill_name = skill_meta.get("skill_name")
                skill = state.orch._find_skill(skill_name) if state.orch else None
                args = skill_meta.get("args", {})
                topic = (
                    args.get("topic")
                    or args.get("theme")
                    or args.get("scenario")
                    or args.get("episode_theme")
                    or ""
                )
                current_style = args.get("style")
                available_styles = getattr(skill, "available_styles", []) if skill else []
                if available_styles:
                    suggestion = SuggestionResponse(
                        skill_name=skill_name,
                        skill_type="creative",
                        topic=topic,
                        current_style=current_style,
                        available_styles=[s for s in available_styles if s != current_style],
                        prompt_template="使用 {skill_name} 技能，主题是【{topic}】，风格改成【{style}】",
                    )

            # 扣费
            if state.memory is not None:
                state.memory.deduct_tokens(user_id, CHAT_COST)

            return ChatResponse(
                output=result["output"], session_id=session_id, model=model_used, messages=messages, suggestion=suggestion
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


STANDUP_COST = 18

@app.post("/skills/standup", response_model=StandupResponse, tags=["skills"])
async def skill_standup(
    request: StandupRequest, user_id: str = Depends(get_current_user)
) -> StandupResponse:
    """直接调用脱口秀创作 Skill。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    if state.memory is not None:
        account = state.memory.get_token_account(user_id)
        if account.balance < STANDUP_COST:
            raise HTTPException(status_code=402, detail=f"Token 余额不足（需 {STANDUP_COST}，余 {account.balance}）")

    # 优先复用 orchestrator 中已注册的 Skill，保证模型上下文一致
    skill = None
    for tool in state.orch.tools:
        if getattr(tool, "name", None) == "standup":
            skill = tool
            break

    # 若未注册，则新建（兼容测试与边缘场景）
    if skill is None:
        skill = StandupSkill()

    # 若前端指定了模型，覆盖 Skill 的模型
    if request.model is not None:
        skill.model_name = request.model

    try:
        content = skill.invoke(
            {
                "topic": request.topic,
                "style": request.style,
                "duration": request.duration,
                "audience": request.audience,
                "density": request.density,
                "perspective_count": request.perspective_count,
                "user_id": user_id,
                "debug": request.debug,
            }
        )
        if state.memory is not None:
            state.memory.deduct_tokens(user_id, STANDUP_COST)
        return StandupResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


SKETCH_COST = 18

@app.post("/skills/sketch", response_model=SketchResponse, tags=["skills"])
async def skill_sketch(
    request: SketchRequest, user_id: str = Depends(get_current_user)
) -> SketchResponse:
    """直接调用小品创作 Skill。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    if state.memory is not None:
        account = state.memory.get_token_account(user_id)
        if account.balance < SKETCH_COST:
            raise HTTPException(status_code=402, detail=f"Token 余额不足（需 {SKETCH_COST}，余 {account.balance}）")

    skill = None
    for tool in state.orch.tools:
        if getattr(tool, "name", None) == "sketch_generator":
            skill = tool
            break

    if skill is None:
        skill = SketchSkill()

    if request.model is not None:
        skill.model_name = request.model

    try:
        content = skill.invoke(
            {
                "theme": request.theme,
                "style": request.style,
                "characters_count": request.characters_count,
                "setting": request.setting,
                "duration": request.duration,
                "conflict_type": request.conflict_type,
                "user_id": user_id,
            }
        )
        if state.memory is not None:
            state.memory.deduct_tokens(user_id, SKETCH_COST)
        return SketchResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


MANZAI_COST = 18

@app.post("/skills/manzai", response_model=ManzaiResponse, tags=["skills"])
async def skill_manzai(
    request: ManzaiRequest, user_id: str = Depends(get_current_user)
) -> ManzaiResponse:
    """直接调用漫才创作 Skill。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    if state.memory is not None:
        account = state.memory.get_token_account(user_id)
        if account.balance < MANZAI_COST:
            raise HTTPException(status_code=402, detail=f"Token 余额不足（需 {MANZAI_COST}，余 {account.balance}）")

    skill = None
    for tool in state.orch.tools:
        if getattr(tool, "name", None) == "manzai_generator":
            skill = tool
            break

    if skill is None:
        skill = ManzaiSkill()

    if request.model is not None:
        skill.model_name = request.model

    try:
        content = skill.invoke(
            {
                "topic": request.topic,
                "style": request.style,
                "duration": request.duration,
                "segments_count": request.segments_count,
                "absurd_level": request.absurd_level,
                "user_id": user_id,
            }
        )
        if state.memory is not None:
            state.memory.deduct_tokens(user_id, MANZAI_COST)
        return ManzaiResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


JAPANESE_SKETCH_COST = 18

@app.post("/skills/japanese-sketch", response_model=JapaneseSketchResponse, tags=["skills"])
async def skill_japanese_sketch(
    request: JapaneseSketchRequest, user_id: str = Depends(get_current_user)
) -> JapaneseSketchResponse:
    """直接调用日式短剧创作 Skill。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    if state.memory is not None:
        account = state.memory.get_token_account(user_id)
        if account.balance < JAPANESE_SKETCH_COST:
            raise HTTPException(status_code=402, detail=f"Token 余额不足（需 {JAPANESE_SKETCH_COST}，余 {account.balance}）")

    skill = None
    for tool in state.orch.tools:
        if getattr(tool, "name", None) == "japanese_sketch_generator":
            skill = tool
            break

    if skill is None:
        skill = JapaneseSketchSkill()

    if request.model is not None:
        skill.model_name = request.model

    try:
        content = skill.invoke(
            {
                "theme": request.theme,
                "style": request.style,
                "characters_count": request.characters_count,
                "setting": request.setting,
                "duration": request.duration,
                "character_type": request.character_type,
                "punchline_density": request.punchline_density,
                "user_id": user_id,
            }
        )
        if state.memory is not None:
            state.memory.deduct_tokens(user_id, JAPANESE_SKETCH_COST)
        return JapaneseSketchResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------ #
# 作品管理路由
# ------------------------------------------------------------------ #
@app.post("/scripts", response_model=ScriptData, tags=["scripts"])
async def create_script(
    request: ScriptCreateRequest, user_id: str = Depends(get_current_user)
) -> ScriptData:
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
    return state.memory.save_script(user_id, script)


@app.get("/scripts", response_model=ScriptListResponse, tags=["scripts"])
async def list_scripts(
    script_type: str | None = None,
    user_id: str = Depends(get_current_user),
) -> ScriptListResponse:
    """列出用户的作品。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    scripts = state.memory.list_scripts(user_id, script_type)
    return ScriptListResponse(scripts=scripts)


@app.get("/scripts/{script_id}", response_model=ScriptDetailResponse, tags=["scripts"])
async def get_script(
    script_id: str, user_id: str = Depends(get_current_user)
) -> ScriptDetailResponse:
    """获取单个作品详情。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    script = state.memory.load_script(script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    return ScriptDetailResponse(script=script)


@app.put("/scripts/{script_id}", response_model=ScriptData, tags=["scripts"])
async def update_script(
    script_id: str,
    request: ScriptUpdateRequest,
    user_id: str = Depends(get_current_user),
) -> ScriptData:
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
    return state.memory.save_script(user_id, updated)


@app.delete("/scripts/{script_id}", response_model=SuccessResponse, tags=["scripts"])
async def delete_script(
    script_id: str, user_id: str = Depends(get_current_user)
) -> SuccessResponse:
    """删除作品。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    ok = state.memory.delete_script(script_id)
    if not ok:
        raise HTTPException(status_code=404, detail="作品不存在")
    return SuccessResponse(success=True)


@app.patch("/scripts/{script_id}/rate", response_model=SuccessResponse, tags=["scripts"])
async def rate_script(
    script_id: str,
    request: ScriptRateRequest,
    user_id: str = Depends(get_current_user),
) -> SuccessResponse:
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
async def feedback_ingest(
    request: FeedbackIngestRequest,
    user_id: str = Depends(get_current_user),
) -> FeedbackIngestResponse:
    """将用户高评分剧本回流到知识库，实现持续进化。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    tracer = get_tracer()
    metrics = get_metrics()

    try:
        with tracer.span(
            "api.feedback_ingest",
            input_data={"user_id": user_id, "min_rating": request.min_rating},
            metadata={"endpoint": "/feedback/ingest"},
        ) as span:
            loop = FeedbackLoop(
                memory=state.memory,
                min_rating=request.min_rating if request.min_rating is not None else 4.0,
            )
            result = loop.ingest_high_rated_scripts(
                user_id=user_id,
                chunk_strategy=request.chunk_strategy or "paragraph",
                dry_run=request.dry_run,
            )
            span.output_data = result
            metrics.record("api.feedback_ingest.duration_ms", span.duration_ms)
            return FeedbackIngestResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------ #
# 会话管理路由
# ------------------------------------------------------------------ #
@app.get("/conversations", tags=["conversations"])
async def list_conversations(
    limit: int = 10,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """列出当前用户的近期会话。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    conversations = state.memory.list_conversations(user_id, limit=limit)
    return {
        "conversations": [
            {
                "session_id": c.session_id,
                "summary": c.summary,
                "message_count": len(c.messages),
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in conversations
        ]
    }


@app.get("/conversations/{session_id}", tags=["conversations"])
async def get_conversation(
    session_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """获取单个会话的完整聊天记录。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    conv = state.memory.load_conversation(user_id, session_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return {
        "session_id": conv.session_id,
        "messages": conv.messages,
        "summary": conv.summary,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }


@app.delete("/conversations/{session_id}", response_model=SuccessResponse, tags=["conversations"])
async def delete_conversation(
    session_id: str,
    user_id: str = Depends(get_current_user),
) -> SuccessResponse:
    """删除指定会话。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    ok = state.memory.delete_conversation(user_id, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SuccessResponse(success=True)


# ------------------------------------------------------------------ #
# 文档管理路由
# ------------------------------------------------------------------ #
@app.post("/documents/upload", response_model=list[DocumentUploadResponse], tags=["documents"])
async def upload_documents(
    files: list[UploadFile] = File(...),
    kind: str | None = Form(default=None, description="喜剧种类标识，如 standup / sketch / manzai"),
    style: str | None = Form(default=None, description="风格标识，如 traditional / modern / 自嘲"),
    chunk_strategy: str = Form(default="paragraph", description="分块策略：fixed / paragraph / scene / dialogue / subtitle"),
    topic: str | None = Form(default=None, description="文档主题/话题，如：职场加班、相亲经历"),
    user_id: str = Depends(get_current_user),
) -> list[DocumentUploadResponse]:
    """上传文档到个人知识库。支持多文件上传，自动解析并入库。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    results: list[DocumentUploadResponse] = []
    upload_dir = Path(settings.data_dir) / "uploads" / user_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        safe_name = Path(file.filename or "unknown").name
        save_path = upload_dir / safe_name
        # 若重名则加序号
        counter = 1
        original_save_path = save_path
        while save_path.exists():
            stem = original_save_path.stem
            suffix = original_save_path.suffix
            save_path = upload_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        # 保存文件
        content = await file.read()
        save_path.write_bytes(content)

        # 创建文档记录
        doc = DocumentData(
            user_id=user_id,
            filename=safe_name,
            kind=kind,
            style=style,
            chunk_strategy=chunk_strategy,
            topic=topic,
            status="pending",
        )
        doc = state.memory.save_document(doc)

        # 导入知识库
        try:
            ingestor = KnowledgeIngestor(
                retriever=None,
                chunk_strategy=chunk_strategy,
            )
            # 使用用户个人向量库
            user_vector_store = VectorStore(
                collection_name=f"user_knowledge_{user_id}",
                persist_path=str(settings.vector_db_path),
            )
            user_retriever = ComedyRetriever(vector_store=user_vector_store)
            ingestor.retriever = user_retriever
            result = ingestor.ingest_file(save_path, kind=kind, style=style)

            # 更新状态
            doc.status = "ingested"
            doc.chunk_count = result.get("chunks", 0)
            state.memory.save_document(doc)

            results.append(
                DocumentUploadResponse(
                    doc_id=doc.doc_id,
                    filename=safe_name,
                    kind=kind,
                    style=style,
                    chunk_strategy=chunk_strategy,
                    topic=topic,
                    status="ingested",
                    chunks=result.get("chunks", 0),
                )
            )
        except Exception as e:
            err_text = str(e)
            # 给常见错误更友好的提示
            if "429" in err_text and "quota" in err_text.lower():
                err_text = "OpenAI API 配额不足，请切换 Embedding 模型（如 hf-local）或充值"
            elif "429" in err_text:
                err_text = "API 请求过于频繁，请稍后再试"
            elif "401" in err_text or "Unauthorized" in err_text:
                err_text = "API Key 无效或未配置"
            elif "Connection" in err_text or "Timeout" in err_text:
                err_text = "网络连接超时，请检查网络或切换本地模型"
            doc.status = "failed"
            doc.error_msg = err_text
            state.memory.save_document(doc)
            results.append(
                DocumentUploadResponse(
                    doc_id=doc.doc_id,
                    filename=safe_name,
                    kind=kind,
                    style=style,
                    chunk_strategy=chunk_strategy,
                    topic=topic,
                    status="failed",
                    chunks=0,
                )
            )
    return results


@app.get("/documents", response_model=DocumentListResponse, tags=["documents"])
async def list_documents(
    user_id: str = Depends(get_current_user),
) -> DocumentListResponse:
    """列出当前用户上传的文档。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    docs = state.memory.list_documents(user_id)
    return DocumentListResponse(documents=docs)


@app.delete("/documents/{doc_id}", response_model=SuccessResponse, tags=["documents"])
async def delete_document(
    doc_id: str,
    user_id: str = Depends(get_current_user),
) -> SuccessResponse:
    """删除指定文档，同时清理向量库中的对应内容。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    doc = state.memory.get_document(user_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 清理向量库（按 source_doc_id 或 doc_id 过滤）
    try:
        user_vector_store = VectorStore(
            collection_name=f"user_knowledge_{user_id}",
            persist_path=str(settings.vector_db_path),
        )
        # ChromaDB 元数据过滤：匹配 doc_id 或 source_doc_id
        filter_conditions = {
            "$or": [
                {"doc_id": doc_id},
                {"source_doc_id": doc_id},
            ]
        }
        matched = user_vector_store.get_by_filter(filter_conditions)
        if matched:
            ids_to_delete = [m.metadata.get("doc_id") for m in matched if m.metadata.get("doc_id")]
            if ids_to_delete:
                user_vector_store.delete(ids_to_delete)
    except Exception:
        logger.warning("清理向量库文档失败: %s", doc_id, exc_info=True)

    # 删除本地文件
    upload_dir = Path(settings.data_dir) / "uploads" / user_id
    file_path = upload_dir / doc.filename
    if file_path.exists():
        file_path.unlink()

    # 删除数据库记录
    ok = state.memory.delete_document(user_id, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在")
    return SuccessResponse(success=True)


# ------------------------------------------------------------------ #
# 模型路由
# ------------------------------------------------------------------ #
@app.get("/models", tags=["models"])
async def list_models() -> dict[str, Any]:
    """返回当前环境可用的模型列表。"""
    available = ModelFactory.list_available_models()
    default = settings.default_model
    recommended = default if default in available else (available[0] if available else None)
    return {
        "models": available,
        "default": default,
        "recommended": recommended,
    }


# ------------------------------------------------------------------ #
# 评估路由
# ------------------------------------------------------------------ #
class EvaluateScriptRequest(BaseModel):
    """剧本评估请求。"""

    script: str = Field(description="剧本文本内容")
    script_type: str = Field(default="default", description="剧本类型")


class EvaluateScriptResponse(BaseModel):
    """剧本评估响应。"""

    overall_score: float
    punchline_density: float
    dialogue_ratio: float
    structure_completeness: float
    word_diversity: float
    colloquial_score: float
    length_score: float
    readability: float
    suggestions: list[str]


class EvaluateOutputRequest(BaseModel):
    """模型输出评估请求。"""

    output: str = Field(description="模型输出文本")
    expected_format: str | None = Field(default=None, description="期望格式")


class EvaluateOutputResponse(BaseModel):
    """模型输出评估响应。"""

    overall_score: float
    format_compliance: float
    repetition_score: float
    structure_score: float
    length_score: float
    has_punchline: bool
    has_dialogue: bool
    suggestions: list[str]


@app.post("/evaluate/script", response_model=EvaluateScriptResponse, tags=["evaluation"])
async def evaluate_script(request: EvaluateScriptRequest) -> EvaluateScriptResponse:
    """评估剧本质量（基于规则/启发式指标）。"""
    evaluator = ScriptQualityEvaluator()
    result = evaluator.evaluate(script=request.script, script_type=request.script_type)
    return EvaluateScriptResponse(**result.to_dict())


@app.post("/evaluate/output", response_model=EvaluateOutputResponse, tags=["evaluation"])
async def evaluate_output(request: EvaluateOutputRequest) -> EvaluateOutputResponse:
    """评估模型输出质量。"""
    evaluator = ModelOutputEvaluator()
    result = evaluator.evaluate(
        output=request.output, expected_format=request.expected_format
    )
    return EvaluateOutputResponse(**result.to_dict())


# ------------------------------------------------------------------ #
# 学习模式路由
# ------------------------------------------------------------------ #
@app.post("/learn/chat", response_model=LearnChatResponse, tags=["learn"])
async def learn_chat(
    request: LearnChatRequest,
    user_id: str = Depends(get_current_user),
) -> LearnChatResponse:
    """学习模式对话：针对用户上传的文档进行问答、分析、技巧提取。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    # 1. 从用户个人知识库检索相关文档
    try:
        user_vector_store = VectorStore(
            collection_name=f"user_knowledge_{user_id}",
            persist_path=str(settings.vector_db_path),
        )
        filter_dict = None
        if request.doc_ids:
            # ChromaDB where 过滤：source_doc_id 在列表中
            filter_dict = {"source_doc_id": {"$in": request.doc_ids}}
        docs = user_vector_store.search(request.query, top_k=5, filter_dict=filter_dict)
    except Exception as e:
        logger.warning("学习模式检索失败: %s", e)
        docs = []

    if not docs:
        return LearnChatResponse(
            output="未在个人知识库中找到相关资料。请先上传相关文档。",
            references=[],
        )

    # 2. 格式化参考资料
    references: list[dict[str, Any]] = []
    ref_lines: list[str] = []
    for idx, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "未知来源")
        text = doc.page_content.strip()
        ref_lines.append(f"[{idx}] 来源: {source}\n{text}")
        references.append({"source": source, "content": text[:200]})
    references_text = "\n\n".join(ref_lines)

    # 3. 渲染学习模式 Prompt
    pm = PromptManager()
    try:
        system_prompt = pm.render(
            "learn_system",
            variables={"references": references_text},
        )
    except Exception:
        system_prompt = (
            "你是一位资深喜剧理论导师。请基于以下参考资料回答用户问题。\n\n"
            f"{references_text}"
        )

    # 4. 调用 LLM
    try:
        llm = ModelFactory.get_model(task_type="analytical")
        messages = [
            ("system", system_prompt),
            ("human", f"【分析模式】{request.mode}\n\n【问题】{request.query}"),
        ]
        result = llm.invoke(messages)
        output = str(result.content) if hasattr(result, "content") else str(result)
    except Exception as e:
        logger.warning("学习模式 LLM 调用失败: %s", e)
        raise HTTPException(status_code=500, detail=f"AI 分析失败: {e}")

    return LearnChatResponse(output=output, references=references)


# ------------------------------------------------------------------ #
# 技巧库路由
# ------------------------------------------------------------------ #
@app.post("/learn/cards", response_model=KnowledgeCardData, tags=["learn"])
async def create_knowledge_card(
    request: KnowledgeCardData,
    user_id: str = Depends(get_current_user),
) -> KnowledgeCardData:
    """创建知识卡片（技巧/概念/公式/模式）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    card = KnowledgeCardData(
        user_id=user_id,
        title=request.title,
        content=request.content,
        card_type=request.card_type,
        tags=request.tags,
        source_doc_id=request.source_doc_id,
    )
    return state.memory.save_knowledge_card(card)


@app.get("/learn/cards", response_model=KnowledgeCardListResponse, tags=["learn"])
async def list_knowledge_cards(
    card_type: str | None = None,
    tag: str | None = None,
    user_id: str = Depends(get_current_user),
) -> KnowledgeCardListResponse:
    """列出当前用户的知识卡片。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    cards = state.memory.list_knowledge_cards(user_id, card_type=card_type, tag=tag)
    return KnowledgeCardListResponse(cards=cards)


@app.delete("/learn/cards/{card_id}", response_model=SuccessResponse, tags=["learn"])
async def delete_knowledge_card(
    card_id: str,
    user_id: str = Depends(get_current_user),
) -> SuccessResponse:
    """删除指定知识卡片。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    ok = state.memory.delete_knowledge_card(user_id, card_id)
    if not ok:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return SuccessResponse(success=True)


# ------------------------------------------------------------------ #
# Debug 路由 —— 知识库检索调试
# ------------------------------------------------------------------ #
class DebugRetrieveRequest(BaseModel):
    """检索调试请求。"""

    query: str = Field(description="测试查询")


@app.post("/debug/retrieve", tags=["debug"])
async def debug_retrieve(
    request: DebugRetrieveRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """调试知识库检索：输入查询，返回检索到的文档和 Prompt 注入片段。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator 未就绪")
    result = state.orch.debug_retrieval(request.query, user_id=user_id)
    return result


# ------------------------------------------------------------------ #
# 可观测性路由
# ------------------------------------------------------------------ #
@app.get("/metrics", tags=["observability"])
async def metrics_endpoint() -> dict[str, Any]:
    """返回最近调用链与聚合指标（内部调试用）。"""
    tracer = get_tracer()
    metrics = get_metrics()

    recent_spans = tracer.get_recent(n=20)
    return {
        "trace_stats": tracer.get_stats(),
        "recent_traces": [s.to_dict() for s in recent_spans],
        "metrics": metrics.get_all(),
    }
