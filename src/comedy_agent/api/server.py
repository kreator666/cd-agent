"""FastAPI HTTP 服务入口。

提供 RESTful API 供内部调试与前端对接。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.agent.orchestrator import AgentOrchestrator
from comedy_agent.models.factory import ModelConfigError
from comedy_agent.skills.standup import StandupSkill


# ------------------------------------------------------------------ #
# 请求/响应模型
# ------------------------------------------------------------------ #
class ChatRequest(BaseModel):
    """聊天请求。"""

    prompt: str = Field(description="用户输入")
    model: str | None = Field(default=None, description="指定模型")
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
# 应用生命周期
# ------------------------------------------------------------------ #
class AppState:
    """全局应用状态（持有 Orchestrator 实例）。"""

    def __init__(self) -> None:
        self.orch: AgentOrchestrator | None = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化 Orchestrator。"""
    try:
        state.orch = AgentOrchestrator()
        state.orch.register_skill(StandupSkill())
    except ModelConfigError as e:
        import logging

        logging.getLogger("comedy-agent").error("模型配置错误: %s", e)
        state.orch = None
    yield
    state.orch = None


app = FastAPI(
    title="Comedy Agent API",
    description="喜剧行业垂直 Agent HTTP 接口",
    version="0.1.0",
    lifespan=lifespan,
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
