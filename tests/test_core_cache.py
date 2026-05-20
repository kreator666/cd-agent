"""测试缓存基础设施。"""

import time

import pytest

from comedy_agent.core.cache import MemoryCache, RedisCache


class TestMemoryCache:
    """内存缓存测试。"""

    def test_set_and_get(self):
        cache = MemoryCache()
        cache.set("key1", "value1", ttl=60)
        assert cache.get("key1") == "value1"

    def test_get_missing(self):
        cache = MemoryCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        cache = MemoryCache()
        cache.set("key2", "value2", ttl=1)
        assert cache.get("key2") == "value2"
        time.sleep(1.1)
        assert cache.get("key2") is None

    def test_delete(self):
        cache = MemoryCache()
        cache.set("key3", "value3")
        cache.delete("key3")
        assert cache.get("key3") is None

    def test_json_roundtrip(self):
        cache = MemoryCache()
        cache.set_json("j1", {"a": 1, "b": [2, 3]})
        assert cache.get_json("j1") == {"a": 1, "b": [2, 3]}

    def test_lru_eviction(self):
        cache = MemoryCache(max_size=3)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.set("k3", "v3")
        cache.get("k1")  # 访问 k1，使其变为最近使用
        cache.set("k4", "v4")  # 应淘汰最久未使用的 k2
        assert cache.get("k1") is not None
        assert cache.get("k2") is None
        assert cache.get("k3") is not None
        assert cache.get("k4") is not None


class TestRedisCache:
    """Redis 缓存测试（Redis 不可用时自动跳过）。"""

    @pytest.fixture
    def redis_cache(self):
        cache = RedisCache()
        if not cache.available:
            pytest.skip("Redis 不可用")
        # 清理测试键
        cache.delete("test:cache:key1")
        cache.delete("test:cache:j1")
        return cache

    def test_set_and_get(self, redis_cache: RedisCache):
        redis_cache.set("test:cache:key1", "hello", ttl=10)
        assert redis_cache.get("test:cache:key1") == "hello"

    def test_delete(self, redis_cache: RedisCache):
        redis_cache.set("test:cache:key1", "world")
        redis_cache.delete("test:cache:key1")
        assert redis_cache.get("test:cache:key1") is None

    def test_json_roundtrip(self, redis_cache: RedisCache):
        redis_cache.set_json("test:cache:j1", {"list": [1, 2, 3]})
        assert redis_cache.get_json("test:cache:j1") == {"list": [1, 2, 3]}

    def test_ttl_expiration(self, redis_cache: RedisCache):
        redis_cache.set("test:cache:key1", "x", ttl=1)
        assert redis_cache.get("test:cache:key1") == "x"
        time.sleep(1.1)
        assert redis_cache.get("test:cache:key1") is None
