"""限流基础设施 —— Redis + 本地内存兜底。

提供统一的限流接口，优先使用 Redis，Redis 不可用时自动降级到内存限流。
支持滑动窗口计数器算法。
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# RateLimiter 抽象基类
# ------------------------------------------------------------------ #


class RateLimiter(ABC):
    """限流器抽象基类。"""

    @abstractmethod
    def is_allowed(
        self, key: str, max_requests: int, window_seconds: int
    ) -> bool:
        """判断当前请求是否允许通过。

        Args:
            key: 限流键（如 IP + 路径）。
            max_requests: 窗口内最大请求数。
            window_seconds: 窗口大小（秒）。

        Returns:
            bool: ``True`` 表示允许通过。
        """
        ...


# ------------------------------------------------------------------ #
# RedisRateLimiter —— 基于 Redis 的滑动窗口限流
# ------------------------------------------------------------------ #


class RedisRateLimiter(RateLimiter):
    """基于 Redis Sorted Set 的滑动窗口限流器。"""

    def __init__(self, redis_url: str | None = None) -> None:
        self.available = False
        self._client: Any | None = None
        url = redis_url or settings.redis_url
        if not url:
            logger.info("Redis 未配置，跳过 RedisRateLimiter")
            return
        try:
            from redis import Redis

            self._client = Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            self._client.ping()
            self.available = True
            logger.info("RedisRateLimiter 已连接")
        except Exception as e:
            logger.info("RedisRateLimiter 不可用，降级到内存限流: %s", e)

    def is_allowed(
        self, key: str, max_requests: int, window_seconds: int
    ) -> bool:
        if not self.available or self._client is None:
            return True  # Redis 不可用时不限流

        try:
            now = time.time()
            window_start = now - window_seconds

            pipe = self._client.pipeline()
            # 1. 清理窗口外的旧记录
            pipe.zremrangebyscore(key, 0, window_start)
            # 2. 统计当前窗口内记录数
            pipe.zcard(key)
            # 3. 添加当前请求时间戳
            pipe.zadd(key, {str(now): now})
            # 4. 设置过期时间
            pipe.expire(key, window_seconds + 1)

            _, count, _, _ = pipe.execute()
            return count < max_requests
        except Exception as e:
            logger.warning("Redis 限流检查失败: %s", e)
            return True


# ------------------------------------------------------------------ #
# MemoryRateLimiter —— 基于内存的滑动窗口限流
# ------------------------------------------------------------------ #


class MemoryRateLimiter(RateLimiter):
    """基于内存的滑动窗口限流器。"""

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = {}

    def is_allowed(
        self, key: str, max_requests: int, window_seconds: int
    ) -> bool:
        now = time.time()
        window_start = now - window_seconds

        # 获取并清理过期记录
        timestamps = self._windows.get(key, [])
        timestamps = [t for t in timestamps if t > window_start]

        if len(timestamps) < max_requests:
            timestamps.append(now)
            self._windows[key] = timestamps
            return True

        self._windows[key] = timestamps
        return False


# ------------------------------------------------------------------ #
# 工厂函数
# ------------------------------------------------------------------ #


def get_rate_limiter(redis_url: str | None = None) -> RateLimiter:
    """获取可用的限流器实例（Redis 优先，失败则降级到内存限流）。"""
    redis = RedisRateLimiter(redis_url=redis_url)
    if redis.available:
        return redis
    logger.info("使用内存限流器")
    return MemoryRateLimiter()
