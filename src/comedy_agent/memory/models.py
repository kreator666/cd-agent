"""记忆系统 Pydantic 数据模型。

用于层间数据传输、API 序列化与类型校验。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
# 基础模型
# ------------------------------------------------------------------ #
class UserProfileData(BaseModel):
    """用户画像数据。"""

    user_id: str = Field(description="用户唯一标识")
    nickname: str | None = Field(default=None, description="用户昵称")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class PreferenceItem(BaseModel):
    """用户偏好项。"""

    key: str = Field(description="偏好键，如 preferred_style / disliked_tropes")
    value: Any = Field(description="偏好值，任意 JSON 可序列化结构")


class ConversationData(BaseModel):
    """会话数据（短期记忆）。"""

    session_id: str = Field(description="会话唯一标识")
    messages: list[dict[str, Any]] = Field(
        default_factory=list, description="消息列表 [(role, content), ...]"
    )
    summary: str | None = Field(default=None, description="对话摘要")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")
    expires_at: datetime | None = Field(default=None, description="过期时间")


class ScriptData(BaseModel):
    """用户创作作品数据。"""

    script_id: str | None = Field(default=None, description="作品唯一标识，留空则自动生成")
    title: str | None = Field(default=None, description="作品标题")
    content: str = Field(description="作品内容")
    script_type: str | None = Field(
        default=None, description="作品类型：standup / sketch / crosstalk / sitcom"
    )
    rating: float | None = Field(default=None, description="用户评分 0.0-5.0")
    tags: list[str] | None = Field(default=None, description="标签列表")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


# ------------------------------------------------------------------ #
# 聚合模型
# ------------------------------------------------------------------ #
class DocumentData(BaseModel):
    """用户上传文档数据。"""

    doc_id: str | None = Field(default=None, description="文档唯一标识，留空则自动生成")
    user_id: str = Field(description="所属用户")
    filename: str = Field(description="原始文件名")
    doc_type: str | None = Field(default=None, description="文档类型：theory / case / mixed")
    kind: str | None = Field(default=None, description="喜剧种类：standup / sketch / manzai / japanese_sketch / crosstalk / sitcom / general")
    style: str | None = Field(default=None, description="风格标识：traditional / modern / 自嘲 / 讽刺 / 愤怒式 / 荒诞式 / 日常观察")
    chunk_strategy: str | None = Field(default=None, description="分块策略：fixed / paragraph / scene / dialogue / subtitle")
    status: str = Field(default="pending", description="入库状态：pending / ingested / failed")
    chunk_count: int | None = Field(default=None, description="分块数量")
    error_msg: str | None = Field(default=None, description="错误信息")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class KnowledgeCardData(BaseModel):
    """知识卡片数据。"""

    card_id: str | None = Field(default=None, description="卡片唯一标识，留空则自动生成")
    user_id: str = Field(description="所属用户")
    title: str = Field(description="技巧名称")
    content: str = Field(description="技巧内容/说明")
    card_type: str = Field(default="technique", description="卡片类型：technique / concept / formula / pattern")
    tags: list[str] | None = Field(default=None, description="标签列表")
    source_doc_id: str | None = Field(default=None, description="来源文档 ID")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class UserContext(BaseModel):
    """用户完整上下文（用于注入 Agent Prompt）。"""

    profile: UserProfileData | None = None
    preferences: list[PreferenceItem] = Field(default_factory=list)
    recent_conversations: list[ConversationData] = Field(default_factory=list)
    recent_scripts: list[ScriptData] = Field(default_factory=list)
