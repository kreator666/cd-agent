"""
多平台统一发布 orchestrator。

协调各平台适配器完成一键分发。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from comedy_agent.publisher.base_adapter import BasePlatformAdapter
from comedy_agent.publisher.models import ContentItem, PlatformType, PublishResult

logger = logging.getLogger(__name__)


class MultiPlatformPublisher:
    """
    多平台发布协调器。

    管理多个平台适配器，实现一键分发。
    """

    def __init__(self):
        self.adapters: dict[PlatformType, BasePlatformAdapter] = {}
        logger.info("多平台发布协调器初始化完成")

    def register_adapter(self, adapter: BasePlatformAdapter):
        """
        注册平台适配器。

        Args:
            adapter: 平台适配器实例
        """
        self.adapters[adapter.platform_type] = adapter
        logger.info("已注册适配器: %s", adapter.platform_name)

    def unregister_adapter(self, platform_type: PlatformType):
        """注销平台适配器。"""
        if platform_type in self.adapters:
            adapter = self.adapters.pop(platform_type)
            logger.info("已注销适配器: %s", adapter.platform_name)

    async def publish_to_platform(
        self,
        platform: PlatformType,
        content: ContentItem,
    ) -> PublishResult:
        """
        发布到指定平台。

        Args:
            platform: 目标平台
            content: 内容

        Returns:
            PublishResult: 发布结果
        """
        adapter = self.adapters.get(platform)
        if not adapter:
            return PublishResult(
                platform=platform,
                success=False,
                message=f"未找到平台适配器: {platform.value}",
            )

        try:
            # 发布前检查
            ok, msg = adapter.pre_publish_check(content)
            if not ok:
                return PublishResult(
                    platform=platform,
                    success=False,
                    message=f"发布前检查失败: {msg}",
                )

            # 执行发布
            logger.info("[%s] 开始发布: %s", adapter.platform_name, content.title)
            result = await adapter.publish(content)

            if result.success:
                logger.info("[%s] 发布成功: %s", adapter.platform_name, result.message)
            else:
                logger.error("[%s] 发布失败: %s", adapter.platform_name, result.message)

            return result

        except Exception as e:
            logger.exception("[%s] 发布异常", adapter.platform_name)
            return PublishResult(
                platform=platform,
                success=False,
                message=f"发布异常: {e}",
            )

    async def publish_to_all(
        self,
        content: ContentItem,
        platforms: Optional[list[PlatformType]] = None,
        sequential: bool = True,
        delay_seconds: float = 5.0,
    ) -> dict[PlatformType, PublishResult]:
        """
        一键发布到多个平台。

        Args:
            content: 统一内容模型
            platforms: 目标平台列表，None表示所有已注册平台
            sequential: 是否串行发布（推荐，避免风控）
            delay_seconds: 平台间延迟秒数

        Returns:
            Dict[PlatformType, PublishResult]: 各平台发布结果
        """
        target_platforms = platforms or list(self.adapters.keys())
        results = {}

        logger.info("开始一键分发到 %s 个平台", len(target_platforms))

        if sequential:
            # 串行发布（推荐，降低风控风险）
            for platform in target_platforms:
                result = await self.publish_to_platform(platform, content)
                results[platform] = result

                # 平台间延迟
                if platform != target_platforms[-1]:
                    logger.info("等待 %s 秒后发布到下一个平台...", delay_seconds)
                    await asyncio.sleep(delay_seconds)
        else:
            # 并行发布
            tasks = [
                self.publish_to_platform(p, content)
                for p in target_platforms
            ]
            platform_results = await asyncio.gather(*tasks, return_exceptions=True)

            for platform, result in zip(target_platforms, platform_results):
                if isinstance(result, Exception):
                    results[platform] = PublishResult(
                        platform=platform,
                        success=False,
                        message=f"发布异常: {result}",
                    )
                else:
                    results[platform] = result

        # 输出汇总
        self._print_summary(results)
        return results

    def _print_summary(self, results: dict[PlatformType, PublishResult]):
        """打印发布汇总。"""
        logger.info("=" * 60)
        logger.info("发布汇总")
        logger.info("=" * 60)

        for platform, result in results.items():
            status = "成功" if result.success else "失败"
            logger.info("[%s] %s: %s", platform.value, status, result.message)
            if result.url:
                logger.info("    链接: %s", result.url)
            if result.needs_manual_confirm:
                logger.info("    需要手动确认: %s", result.confirm_url or "请查看二维码")

        success_count = sum(1 for r in results.values() if r.success)
        total = len(results)
        logger.info("-" * 60)
        logger.info("总计: %s/%s 个平台发布成功", success_count, total)
        logger.info("=" * 60)

    async def check_all_login_status(self) -> dict[PlatformType, bool]:
        """
        检查所有平台的登录状态。

        Returns:
            Dict[PlatformType, bool]: 各平台登录状态
        """
        results = {}
        for platform_type, adapter in self.adapters.items():
            try:
                is_login = await adapter.check_login_status()
                results[platform_type] = is_login
                status = "已登录" if is_login else "未登录"
                logger.info("[%s] 登录状态: %s", adapter.platform_name, status)
            except Exception as e:
                logger.error("[%s] 检查登录状态失败: %s", adapter.platform_name, e)
                results[platform_type] = False
        return results

    async def cleanup_all(self):
        """清理所有适配器资源。"""
        for adapter in self.adapters.values():
            try:
                adapter.cleanup()
            except Exception as e:
                logger.error("[%s] 资源清理失败: %s", adapter.platform_name, e)
