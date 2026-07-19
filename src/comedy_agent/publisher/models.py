"""
多平台发布数据模型。

为 B站等平台提供统一的内容模型与发布结果模型。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class PlatformType(str, Enum):
    """支持的平台类型。"""

    XIAOHONGSHU = "xiaohongshu"      # 小红书
    DOUYIN = "douyin"                # 抖音
    WECHAT_VIDEO = "wechat_video"    # 微信视频号
    BILIBILI = "bilibili"            # B站


@dataclass
class ContentItem:
    """
    统一内容数据模型。

    一次创作，适配多个平台。
    """

    # 基础内容
    title: str                          # 标题
    content: str                        # 正文/描述

    # 媒体资源
    video_path: Optional[str] = None    # 视频文件路径（视频内容必填）
    image_paths: list[str] = field(default_factory=list)  # 图片路径列表（图文内容）
    cover_path: Optional[str] = None    # 封面图路径

    # 平台适配
    tags: list[str] = field(default_factory=list)  # 标签/话题
    location: Optional[str] = None      # 地理位置

    # 各平台特化字段（可选）
    platform_extra: dict[PlatformType, dict[str, Any]] = field(default_factory=dict)

    # 发布设置
    scheduled_time: Optional[datetime] = None  # 定时发布时间

    def get_platform_title(self, platform: PlatformType, max_length: int | None = None) -> str:
        """获取适配平台的长度限制的标题。"""
        extra = self.platform_extra.get(platform, {})
        title = extra.get("title", self.title)
        if max_length and len(title) > max_length:
            title = title[:max_length - 3] + "..."
        return title

    def get_platform_content(self, platform: PlatformType) -> str:
        """获取适配平台的内容。"""
        extra = self.platform_extra.get(platform, {})
        return extra.get("content", self.content)

    def get_platform_tags(self, platform: PlatformType) -> list[str]:
        """获取适配平台的标签。"""
        extra = self.platform_extra.get(platform, {})
        return extra.get("tags", self.tags)


@dataclass
class PublishResult:
    """发布结果。"""

    platform: PlatformType
    success: bool
    message: str
    url: Optional[str] = None           # 发布后的链接
    content_id: Optional[str] = None    # 平台内容ID
    timestamp: datetime = field(default_factory=datetime.now)
    raw_response: Optional[dict[str, Any]] = None  # 原始响应
    needs_manual_confirm: bool = False   # 是否需要用户手动确认
    confirm_url: Optional[str] = None    # 手动确认URL
    qrcode_path: Optional[str] = None    # 确认二维码图片路径
