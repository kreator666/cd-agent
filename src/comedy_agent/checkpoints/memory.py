"""MemorySaver checkpoint 配置。

开发阶段使用内存持久化，Phase 6 替换为 AsyncPostgresSaver。
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

# 允许 checkpoint serde 反序列化的自定义模块类型。
# 若不在此列，LangGraph 会报 "Deserializing unregistered type ..." 警告，
# 未来版本将直接阻断。
_ALLOWED_MSGPACK_MODULES = [
    ("comedy_agent.agents.schemas", "ReviewDecision"),
]

_serde = JsonPlusSerializer(
    allowed_msgpack_modules=_ALLOWED_MSGPACK_MODULES,
)


class MemorySaverFactory:
    """MemorySaver 单例工厂。"""

    _instance: MemorySaver | None = None

    @classmethod
    def get(cls) -> MemorySaver:
        """获取全局唯一的 MemorySaver 实例。"""
        if cls._instance is None:
            cls._instance = MemorySaver(serde=_serde)
        return cls._instance


def get_memory_saver() -> MemorySaver:
    """获取 MemorySaver 实例。"""
    return MemorySaverFactory.get()
