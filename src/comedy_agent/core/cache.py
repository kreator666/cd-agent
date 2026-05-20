"""缓存基础设施 —— Redis + 本地内存兜底。

提供统一的缓存接口，优先使用 Redis，Redis 不可用时自动降级到内存缓存。
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any

from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Cache 抽象基类
# ------------------------------------------------------------------ #


class Cache(ABC):
    """缓存抽象基类。"""

    @abstractmethod
    def get(self, key: str) -> str | None:
        """获取缓存值。"""
        ...

    @abstractmethod
    def set(self, key: str, value: str, ttl: int = 300) -> None:
        """设置缓存值，ttl 单位为秒。"""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除缓存键。"""
        ...

    def get_json(self, key: str) -> Any | None:
        """获取 JSON 缓存值并反序列化。"""
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("缓存值不是有效 JSON: %s", key)
            return None

    def set_json(self, key: str, value: Any, ttl: int = 300) -> None:
        """序列化后存入缓存。"""
        self.set(key, json.dumps(value, ensure_ascii=False, default=str), ttl=ttl)


# ------------------------------------------------------------------ #
# RedisCache
# ------------------------------------------------------------------ #


class RedisCache(Cache):
    """Redis 缓存实现。"""

    def __init__(self, redis_url: str | None = None) -> None:
        self.available = False
        self._client: Any | None = None
        try:
            from redis import Redis

            self._client = Redis.from_url(
                redis_url or settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._client.ping()
            self.available = True
            logger.info("RedisCache 已连接")
        except Exception as e:
            logger.warning("RedisCache 初始化失败，将降级到内存缓存: %s", e)

    def get(self, key: str) -> str | None:
        if not self.available or self._client is None:
            return None
        try:
            return self._client.get(key)
        except Exception as e:
            logger.warning("Redis get 失败: %s", e)
            return None

    def set(self, key: str, value: str, ttl: int = 300) -> None:
        if not self.available or self._client is None:
            return
        try:
            self._client.setex(key, ttl, value)
        except Exception as e:
            logger.warning("Redis set 失败: %s", e)

    def delete(self, key: str) -> None:
        if not self.available or self._client is None:
            return
        try:
            self._client.delete(key)
        except Exception as e:
            logger.warning("Redis delete 失败: %s", e)


# ------------------------------------------------------------------ #
# MemoryCache
# ------------------------------------------------------------------ #


class MemoryCache(Cache):
    """本地内存缓存，带 TTL 和 LRU 淘汰。"""

    def __init__(self, max_size: int = 1000) -> None:
        self._data: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> str | None:
        if key not in self._data:
            return None
        value, expire_at = self._data[key]
        if time.time() > expire_at:
            del self._data[key]
            return None
        # LRU：移到末尾表示最近使用
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: str, ttl: int = 300) -> None:
        now = time.time()
        # 清理过期项
        self._evict_expired(now)
        # LRU 淘汰
        if len(self._data) >= self._max_size and key not in self._data:
            self._data.popitem(last=False)
        self._data[key] = (value, now + ttl)
        self._data.move_to_end(key)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def _evict_expired(self, now: float) -> None:
        expired = [k for k, (_, exp) in self._data.items() if now > exp]
        for k in expired:
            del self._data[k]


# ------------------------------------------------------------------ #
# 工厂函数
# ------------------------------------------------------------------ #


def get_cache(redis_url: str | None = None) -> Cache:
    """获取可用的缓存实例（Redis 优先，失败则降级到内存缓存）。"""
    redis = RedisCache(redis_url=redis_url)
    if redis.available:
        return redis
    logger.info("使用内存缓存")
    return MemoryCache()
