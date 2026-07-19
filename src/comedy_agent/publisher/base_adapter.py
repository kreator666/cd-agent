"""
平台适配器基类 - 定义统一接口。

所有平台适配器必须继承此类并实现抽象方法。
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from comedy_agent.publisher.models import ContentItem, PlatformType, PublishResult

logger = logging.getLogger(__name__)


class BasePlatformAdapter(ABC):
    """
    平台适配器抽象基类。

    采用适配器模式，为不同平台提供统一的发布接口。
    """

    def __init__(self, config: dict | None = None):
        """
        初始化适配器。

        Args:
            config: 平台相关配置字典。
        """
        self.config = config or {}
        self._is_logged_in = False
        logger.info("[%s] 适配器初始化完成", self.platform_name)

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """平台名称（中文）。"""
        pass

    @property
    @abstractmethod
    def platform_type(self) -> PlatformType:
        """平台类型枚举。"""
        pass

    @property
    def is_logged_in(self) -> bool:
        """是否已登录。"""
        return self._is_logged_in

    @abstractmethod
    async def login(self, **kwargs) -> bool:
        """
        登录平台。

        Returns:
            bool: 登录是否成功。
        """
        pass

    @abstractmethod
    async def check_login_status(self) -> bool:
        """
        检查登录状态。

        Returns:
            bool: 是否已登录。
        """
        pass

    @abstractmethod
    async def publish(self, content: ContentItem) -> PublishResult:
        """
        发布内容到平台。

        Args:
            content: 统一内容模型。

        Returns:
            PublishResult: 发布结果。
        """
        pass

    async def pre_publish_check(self, content: ContentItem) -> tuple[bool, str]:
        """
        发布前检查。

        Returns:
            (是否通过, 错误信息)
        """
        # 基础检查
        if not content.title:
            return False, "标题不能为空"

        if not content.content:
            return False, "内容不能为空"

        # 检查媒体资源
        if content.video_path and not self._check_file_exists(content.video_path):
            return False, f"视频文件不存在: {content.video_path}"

        for img_path in content.image_paths:
            if not self._check_file_exists(img_path):
                return False, f"图片文件不存在: {img_path}"

        if content.cover_path and not self._check_file_exists(content.cover_path):
            return False, f"封面文件不存在: {content.cover_path}"

        return True, ""

    def _check_file_exists(self, path: str) -> bool:
        """检查文件是否存在。"""
        return os.path.exists(path) and os.path.isfile(path)

    async def cleanup(self):
        """
        清理资源。

        子类可重写此方法进行资源释放。
        """
        logger.info("[%s] 资源清理完成", self.platform_name)

    def _create_success_result(
        self,
        message: str,
        url: str | None = None,
        content_id: str | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> PublishResult:
        """创建成功结果。"""
        return PublishResult(
            platform=self.platform_type,
            success=True,
            message=message,
            url=url,
            content_id=content_id,
            raw_response=raw_response,
        )

    def _create_failure_result(
        self,
        message: str,
        raw_response: dict[str, Any] | None = None,
    ) -> PublishResult:
        """创建失败结果。"""
        return PublishResult(
            platform=self.platform_type,
            success=False,
            message=message,
            raw_response=raw_response,
        )

    def _create_manual_confirm_result(
        self,
        message: str,
        confirm_url: str | None = None,
        qrcode_path: str | None = None,
    ) -> PublishResult:
        """
        创建需要手动确认的结果。

        适用于小红书等平台需要用户扫码确认的场景。
        """
        return PublishResult(
            platform=self.platform_type,
            success=True,  # 技术上成功提交
            message=message,
            needs_manual_confirm=True,
            confirm_url=confirm_url,
            qrcode_path=qrcode_path,
        )
