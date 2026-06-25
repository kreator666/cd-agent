"""MemorySaver checkpoint 配置。

开发阶段使用内存持久化，Phase 6 替换为 AsyncPostgresSaver。
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver


class MemorySaverFactory:
    """MemorySaver 单例工厂。"""

    _instance: MemorySaver | None = None

    @classmethod
    def get(cls) -> MemorySaver:
        """获取全局唯一的 MemorySaver 实例。"""
        if cls._instance is None:
            cls._instance = MemorySaver()
        return cls._instance


def get_memory_saver() -> MemorySaver:
    """获取 MemorySaver 实例。"""
    return MemorySaverFactory.get()
