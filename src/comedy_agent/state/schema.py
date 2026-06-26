"""LangGraph 状态定义。

v4 重构后的核心状态 Schema，所有 Agent 节点通过该 Schema 传递状态。
Phase 0-1 逐步扩展：从 Chat 到完整创作状态机。
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import AnyMessage
from pydantic import BaseModel, ConfigDict, Field


class ComedyState(BaseModel):
    """喜剧创作 Agent 的全局状态。

    使用 Pydantic BaseModel 实现运行时校验和可序列化。
    节点函数返回的 dict 会被 LangGraph 合并到当前状态中。
    """

    # ------------------------------------------------------------------ #
    # 会话与元信息
    # ------------------------------------------------------------------ #
    phase: Literal[
        "idle",
        "chatting",
        "analyzing",
        "planning",
        "writing",
        "reviewing",
        "human_review",
        "routing_feedback",
        "finalizing",
        "complete",
    ] = Field(
        default="idle",
        description="当前会话阶段",
    )
    session_id: str = Field(
        default="",
        description="会话标识，对应 thread_id",
    )
    user_id: str | None = Field(
        default=None,
        description="用户标识",
    )
    user_input: str = Field(
        default="",
        description="用户当前输入",
    )
    output: str = Field(
        default="",
        description="Agent 最终输出文本",
    )

    # ------------------------------------------------------------------ #
    # 模型与消息
    # ------------------------------------------------------------------ #
    model: str | None = Field(
        default=None,
        description="本次请求指定的模型",
    )
    messages: list[AnyMessage] = Field(
        default_factory=list,
        description="LangChain 消息链",
    )
    chat_history: list[tuple[str, str]] | None = Field(
        default=None,
        description="前端传入的历史消息 [(role, content), ...]",
    )

    # ------------------------------------------------------------------ #
    # 意图与创作流程
    # ------------------------------------------------------------------ #
    intent: Literal["writing", "control", "search", "feedback", "chat"] | None = Field(
        default=None,
        description="用户意图分类",
    )
    analysis: dict[str, Any] | None = Field(
        default=None,
        description="上下文分析结果：话题/态度/偏见/情绪",
    )
    plan: dict[str, Any] | None = Field(
        default=None,
        description="创作计划：todo list + outline",
    )
    current_section: int = Field(
        default=0,
        description="当前写作段落索引",
    )
    sections: list[str] = Field(
        default_factory=list,
        description="已完成的段落文本",
    )
    review: dict[str, Any] | None = Field(
        default=None,
        description="审核结果：decision + comments",
    )
    feedback: str = Field(
        default="",
        description="人类审阅反馈",
    )

    # ------------------------------------------------------------------ #
    # Skill 元信息（复用 v3 约定）
    # ------------------------------------------------------------------ #
    skill_meta: dict[str, Any] | None = Field(
        default=None,
        description="最后一次 Skill 调用的元数据",
    )

    # ------------------------------------------------------------------ #
    # LangGraph interrupt 相关（非 Schema 字段，可能出现在返回 dict 中）
    # ------------------------------------------------------------------ #
    model_config = ConfigDict(extra="allow")
