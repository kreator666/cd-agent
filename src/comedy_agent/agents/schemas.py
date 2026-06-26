"""Worker Agent 结构化输出模型。"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class UserIntent(str, Enum):
    """用户意图枚举。"""

    WRITING = "writing"
    CONTROL = "control"
    SEARCH = "search"
    FEEDBACK = "feedback"
    CHAT = "chat"


class IntentClassification(BaseModel):
    """意图分类结果。"""

    intent: UserIntent = Field(description="用户意图")
    confidence: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="置信度",
    )
    reasoning: str = Field(
        default="",
        description="分类理由，一句话",
    )


class AnalysisResult(BaseModel):
    """上下文四维度分析结果。"""

    topic: str = Field(description="核心话题（10 字以内）")
    attitude: str = Field(
        description="创作者对话题的态度，如讽刺/自嘲/观察/批判/温情"
    )
    bias: str = Field(
        description="可能存在的认知偏见或刻板印象，没有则写'无'"
    )
    emotion: str = Field(
        description="目标情绪基调，如愤怒/荒诞/尴尬/温暖/无奈"
    )


class PlanResult(BaseModel):
    """创作计划结果。"""

    todo: list[str] = Field(description="创作步骤清单")
    outline: list[str] = Field(
        description="段落大纲，每段一句话，通常 3-5 段"
    )
    tone: str = Field(description="整体语气建议")


class ReviewDecision(str, Enum):
    """审核决策枚举。"""

    APPROVE = "通过"
    MODIFY = "修改"
    REWRITE = "重写"


class ReviewResult(BaseModel):
    """段落审核结果。"""

    decision: ReviewDecision = Field(description="审核决策")
    comments: str = Field(
        default="",
        description="具体修改建议，1-3 条",
    )
    score: int = Field(
        default=7,
        ge=1,
        le=10,
        description="质量评分 1-10",
    )


class SearchResultItem(BaseModel):
    """单条搜索结果。"""

    title: str = Field(default="", description="标题")
    snippet: str = Field(description="摘要")
    link: str = Field(default="", description="链接")


class SearchResult(BaseModel):
    """搜索 Worker 输出。"""

    query: str = Field(description="实际搜索查询")
    results: list[SearchResultItem] = Field(
        default_factory=list,
        description="搜索结果列表",
    )
