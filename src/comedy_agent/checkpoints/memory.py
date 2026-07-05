"""Checkpoint 持久化配置。

使用 HybridSqliteSaver 将 LangGraph 状态持久化到 SQLite：
- sync 方法（graph.invoke）使用 sqlite3.Connection
- async 方法（graph.ainvoke，/pro/chat-v4）使用 AsyncSqliteSaver

支持服务重启后恢复会话，同时兼容项目中的 sync 测试。
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)

# 允许 checkpoint serde 反序列化的自定义模块类型。
# 若不在此列，LangGraph 会报 "Deserializing unregistered type ..." 警告，
# 未来版本将直接阻断。
_ALLOWED_MSGPACK_MODULES = [
    ("comedy_agent.agents.schemas", "ReviewDecision"),
]

_serde = JsonPlusSerializer(
    allowed_msgpack_modules=_ALLOWED_MSGPACK_MODULES,
)


class HybridSqliteSaver(BaseCheckpointSaver):
    """同时支持 sync / async 的 SQLite checkpoint saver。

    sync 调用走 sqlite3（避免 asyncio event loop 问题），
    async 调用走 aiosqlite（避免阻塞事件循环）。
    两者共享同一个数据库文件。
    """

    def __init__(self, db_path: str, serde: JsonPlusSerializer = _serde) -> None:
        super().__init__(serde=serde)
        self._db_path = db_path
        self._sync_conn = sqlite3.connect(db_path, check_same_thread=False)
        self._sync_saver = SqliteSaver(self._sync_conn, serde=serde)
        self._async_saver: AsyncSqliteSaver | None = None
        self._lock = asyncio.Lock()

    async def _get_async_saver(self) -> AsyncSqliteSaver:
        if self._async_saver is None:
            async with self._lock:
                if self._async_saver is None:
                    conn = aiosqlite.connect(self._db_path)
                    self._async_saver = AsyncSqliteSaver(conn, serde=self.serde)
        return self._async_saver

    # ------------------------------------------------------------------ #
    # Sync methods -> SqliteSaver
    # ------------------------------------------------------------------ #
    def get(self, config: Any) -> Any:
        return self._sync_saver.get(config)

    def put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        return self._sync_saver.put(config, checkpoint, metadata, new_versions)

    def get_tuple(self, config: Any) -> Any:
        return self._sync_saver.get_tuple(config)

    def list(self, config: Any, **kwargs: Any) -> Any:
        return self._sync_saver.list(config, **kwargs)

    def put_writes(self, config: Any, writes: Any, task_id: Any, task_path: str = "") -> Any:
        return self._sync_saver.put_writes(config, writes, task_id, task_path)

    def get_next_version(self, current: Any, channel: Any) -> Any:
        return self._sync_saver.get_next_version(current, channel)

    def copy_thread(self, config: Any, new_thread_id: str) -> Any:
        return self._sync_saver.copy_thread(config, new_thread_id)

    def delete_thread(self, config: Any) -> Any:
        return self._sync_saver.delete_thread(config)

    def delete_for_runs(self, config: Any, run_ids: list[str]) -> Any:
        return self._sync_saver.delete_for_runs(config, run_ids)

    def get_delta_channel_history(self, config: Any, channel: Any, start: Any, end: Any, **kwargs: Any) -> Any:
        return self._sync_saver.get_delta_channel_history(config, channel, start, end, **kwargs)

    def prune(self, config: Any) -> Any:
        return self._sync_saver.prune(config)

    # ------------------------------------------------------------------ #
    # Async methods -> AsyncSqliteSaver
    # ------------------------------------------------------------------ #
    async def aget(self, config: Any) -> Any:
        saver = await self._get_async_saver()
        return await saver.aget(config)

    async def aput(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        saver = await self._get_async_saver()
        return await saver.aput(config, checkpoint, metadata, new_versions)

    async def aget_tuple(self, config: Any) -> Any:
        saver = await self._get_async_saver()
        return await saver.aget_tuple(config)

    async def alist(self, config: Any, **kwargs: Any) -> Any:
        saver = await self._get_async_saver()
        async for item in saver.alist(config, **kwargs):
            yield item

    async def aput_writes(self, config: Any, writes: Any, task_id: Any, task_path: str = "") -> Any:
        saver = await self._get_async_saver()
        return await saver.aput_writes(config, writes, task_id, task_path)

    async def aget_next_version(self, current: Any, channel: Any) -> Any:
        saver = await self._get_async_saver()
        return await saver.aget_next_version(current, channel)

    async def acopy_thread(self, config: Any, new_thread_id: str) -> Any:
        saver = await self._get_async_saver()
        return await saver.acopy_thread(config, new_thread_id)

    async def adelete_thread(self, config: Any) -> Any:
        saver = await self._get_async_saver()
        return await saver.adelete_thread(config)

    async def adelete_for_runs(self, config: Any, run_ids: list[str]) -> Any:
        saver = await self._get_async_saver()
        return await saver.adelete_for_runs(config, run_ids)

    async def aget_delta_channel_history(
        self, config: Any, channel: Any, start: Any, end: Any, **kwargs: Any
    ) -> Any:
        saver = await self._get_async_saver()
        return await saver.aget_delta_channel_history(config, channel, start, end, **kwargs)

    async def aprune(self, config: Any) -> Any:
        saver = await self._get_async_saver()
        return await saver.aprune(config)


class CheckpointSaverFactory:
    """HybridSqliteSaver 单例工厂。"""

    _instance: HybridSqliteSaver | None = None

    @classmethod
    def get(cls) -> HybridSqliteSaver:
        """获取全局唯一的 HybridSqliteSaver 实例。"""
        if cls._instance is None:
            db_path = settings.memory_db_path
            # 确保数据库文件所在目录存在
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            cls._instance = HybridSqliteSaver(db_path, serde=_serde)
            logger.info("HybridSqliteSaver 已初始化，db_path=%s", db_path)
        return cls._instance


def get_memory_saver() -> HybridSqliteSaver:
    """获取 HybridSqliteSaver 实例。"""
    return CheckpointSaverFactory.get()
