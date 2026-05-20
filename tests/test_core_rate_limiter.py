"""测试限流基础设施。"""

import time

import pytest

from comedy_agent.core.rate_limiter import MemoryRateLimiter, RedisRateLimiter


class TestMemoryRateLimiter:
    """内存限流器测试。"""

    def test_allow_within_limit(self):
        limiter = MemoryRateLimiter()
        key = "user:001"
        for _ in range(5):
            assert limiter.is_allowed(key, max_requests=5, window_seconds=60)

    def test_block_over_limit(self):
        limiter = MemoryRateLimiter()
        key = "user:002"
        for _ in range(3):
            assert limiter.is_allowed(key, max_requests=3, window_seconds=60)
        # 第 4 次应被阻止
        assert not limiter.is_allowed(key, max_requests=3, window_seconds=60)

    def test_window_reset(self):
        limiter = MemoryRateLimiter()
        key = "user:003"
        for _ in range(2):
            assert limiter.is_allowed(key, max_requests=2, window_seconds=1)
        assert not limiter.is_allowed(key, max_requests=2, window_seconds=1)
        time.sleep(1.1)
        # 窗口过期后应允许
        assert limiter.is_allowed(key, max_requests=2, window_seconds=1)

    def test_isolated_keys(self):
        limiter = MemoryRateLimiter()
        assert limiter.is_allowed("user:A", max_requests=1, window_seconds=60)
        assert not limiter.is_allowed("user:A", max_requests=1, window_seconds=60)
        # user:B 不受 user:A 影响
        assert limiter.is_allowed("user:B", max_requests=1, window_seconds=60)


class TestRedisRateLimiter:
    """Redis 限流器测试（Redis 不可用时自动跳过）。"""

    @pytest.fixture
    def redis_limiter(self):
        limiter = RedisRateLimiter()
        if not limiter.available:
            pytest.skip("Redis 不可用")
        return limiter

    def test_allow_within_limit(self, redis_limiter: RedisRateLimiter):
        key = "test:rate:001"
        redis_limiter._client.delete(key)  # type: ignore[union-attr]
        for _ in range(3):
            assert redis_limiter.is_allowed(key, max_requests=3, window_seconds=10)

    def test_block_over_limit(self, redis_limiter: RedisRateLimiter):
        key = "test:rate:002"
        redis_limiter._client.delete(key)  # type: ignore[union-attr]
        for _ in range(2):
            assert redis_limiter.is_allowed(key, max_requests=2, window_seconds=10)
        assert not redis_limiter.is_allowed(key, max_requests=2, window_seconds=10)
        redis_limiter._client.delete(key)  # type: ignore[union-attr]

    def test_window_expiration(self, redis_limiter: RedisRateLimiter):
        key = "test:rate:003"
        redis_limiter._client.delete(key)  # type: ignore[union-attr]
        for _ in range(2):
            assert redis_limiter.is_allowed(key, max_requests=2, window_seconds=1)
        assert not redis_limiter.is_allowed(key, max_requests=2, window_seconds=1)
        time.sleep(1.1)
        assert redis_limiter.is_allowed(key, max_requests=2, window_seconds=1)
        redis_limiter._client.delete(key)  # type: ignore[union-attr]
