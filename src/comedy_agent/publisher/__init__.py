"""
多平台内容发布模块。

将内容一键分发到 B站 等平台。
"""
from comedy_agent.publisher.bilibili import BilibiliAdapter
from comedy_agent.publisher.models import ContentItem, PlatformType, PublishResult
from comedy_agent.publisher.publisher import MultiPlatformPublisher

__all__ = [
    "BilibiliAdapter",
    "ContentItem",
    "MultiPlatformPublisher",
    "PlatformType",
    "PublishResult",
]
