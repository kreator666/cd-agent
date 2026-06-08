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
    source: str = Field(default="chat", description="来源：chat / salt / actor")
    metadata: dict[str, Any] | None = Field(default=None, description="额外元数据")
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
    topic: str | None = Field(default=None, description="文档主题/话题，如：职场加班、相亲经历")
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


# ------------------------------------------------------------------ #
# Token 账户
# ------------------------------------------------------------------ #
class TokenAccountData(BaseModel):
    """用户 Token 账户数据。"""

    user_id: str = Field(description="用户唯一标识")
    balance: int = Field(default=5000, description="Token 余额")
    total_consumed: int = Field(default=0, description="累计消费")
    total_recharged: int = Field(default=0, description="累计充值")
    updated_at: datetime | None = Field(default=None, description="更新时间")


# ------------------------------------------------------------------ #
# 项目
# ------------------------------------------------------------------ #
class ProjectData(BaseModel):
    """项目数据。"""

    project_id: str | None = Field(default=None, description="项目唯一标识，留空则自动生成")
    user_id: str = Field(description="所属用户")
    name: str = Field(description="项目名称")
    project_type: str | None = Field(default=None, description="项目类型：standup / sketch / salt / mixed")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


# ------------------------------------------------------------------ #
# 加点盐历史
# ------------------------------------------------------------------ #
class SaltHistoryData(BaseModel):
    """加点盐历史数据。"""

    salt_id: str | None = Field(default=None, description="记录唯一标识，留空则自动生成")
    user_id: str = Field(description="所属用户")
    project_id: str | None = Field(default=None, description="关联项目 ID")
    original_text: str = Field(description="原始文本")
    polished_text: str = Field(description="润色后文本")
    salt_level: str = Field(description="盐度等级：light / medium / heavy")
    token_cost: int = Field(default=0, description="消耗 Token 数")
    created_at: datetime | None = Field(default=None, description="创建时间")


# ------------------------------------------------------------------ #
# IP 风格模型
# ------------------------------------------------------------------ #
class IPStyleData(BaseModel):
    """IP 风格模型数据（扩展为 IP 角色）。"""

    style_id: str | None = Field(default=None, description="风格唯一标识，留空则自动生成")
    actor_name: str = Field(description="演员名称")
    version: str = Field(description="模型版本")
    description: str = Field(description="风格描述")
    prompt_snippet: str = Field(description="注入 Prompt 的片段")
    status: str = Field(default="active", description="状态：active / testing / offline")
    split_ratio: int = Field(default=70, description="演员分成比例")
    usage_count: int = Field(default=0, description="累计调用次数")
    # --- PRD v2 扩展字段 ---
    avatar_url: str | None = Field(default=None, description="角色头像 URL")
    homepage_background: str | None = Field(default=None, description="主页背景图 URL")
    profile_url: str | None = Field(default=None, description="个人主页路径，如 /ip/lidan")
    follower_count: int = Field(default=0, description="粉丝数")
    is_official: bool = Field(default=False, description="是否官方认证角色")
    skill_id: str | None = Field(default=None, description="关联的风格 Skill ID")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


# ------------------------------------------------------------------ #
# 投稿
# ------------------------------------------------------------------ #
class SubmissionData(BaseModel):
    """投稿数据。"""

    submission_id: str | None = Field(default=None, description="投稿唯一标识，留空则自动生成")
    user_id: str = Field(description="投稿用户")
    script_id: str = Field(description="关联作品 ID")
    target_actor: str = Field(description="目标演员")
    status: str = Field(default="pending", description="状态：pending / adopted / rejected")
    actor_comment: str | None = Field(default=None, description="演员审核意见")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


# ------------------------------------------------------------------ #
# 收益记录
# ------------------------------------------------------------------ #
class EarningRecordData(BaseModel):
    """收益记录数据。"""

    record_id: str | None = Field(default=None, description="记录唯一标识，留空则自动生成")
    user_id: str | None = Field(default=None, description="关联用户（平台收益时为空）")
    actor_name: str | None = Field(default=None, description="演员名称")
    record_type: str = Field(description="记录类型：platform_fee / actor_split / withdrawal")
    amount: int = Field(description="金额（单位：分）")
    description: str | None = Field(default=None, description="说明")
    created_at: datetime | None = Field(default=None, description="创建时间")


# ------------------------------------------------------------------ #
# 敏感词
# ------------------------------------------------------------------ #
class BannedWordData(BaseModel):
    """敏感词数据。"""

    word_id: int | None = Field(default=None, description="敏感词 ID")
    word: str = Field(description="敏感词内容")
    category: str | None = Field(default=None, description="分类：political / competitor / vulgar")
    added_by: str | None = Field(default=None, description="添加者用户 ID")
    created_at: datetime | None = Field(default=None, description="创建时间")
