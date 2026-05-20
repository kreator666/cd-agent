"""可观测性基础设施 —— 调用链追踪、指标收集与 LangSmith 集成。

提供轻量级的调用链追踪（Trace）和指标收集（Metrics），
优先自动接入 LangSmith（若配置了 API Key），同时保留自建日志兜底。
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# LangSmith 自动配置
# ------------------------------------------------------------------ #


def setup_langsmith() -> bool:
    """自动配置 LangSmith 环境变量（若配置了 API Key）。

    Returns:
        bool: 是否成功启用 LangSmith。
    """
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        logger.info("LangSmith 追踪已启用，项目: %s", settings.langsmith_project)
        return True
    return False


# ------------------------------------------------------------------ #
# TraceSpan —— 单个调用段
# ------------------------------------------------------------------ #


@dataclass
class TraceSpan:
    """调用链中的一个段（Span）。"""

    name: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    input_data: Any | None = None
    output_data: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[TraceSpan] = field(default_factory=list)
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        """耗时（毫秒）。"""
        end = self.end_time or time.time()
        return round((end - self.start_time) * 1000, 2)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "input": self._truncate(self.input_data),
            "output": self._truncate(self.output_data),
            "metadata": self.metadata,
            "error": self.error,
            "children": [c.to_dict() for c in self.children],
        }

    @staticmethod
    def _truncate(data: Any, max_len: int = 200) -> Any:
        """截断过长字符串。"""
        if isinstance(data, str) and len(data) > max_len:
            return data[:max_len] + "..."
        return data


# ------------------------------------------------------------------ #
# Tracer —— 调用链追踪器
# ------------------------------------------------------------------ #


class Tracer:
    """调用链追踪器。

    支持嵌套 Span 和上下文管理器，自动维护调用树结构。
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._history: deque[TraceSpan] = deque(maxlen=max_history)
        self._stack: list[TraceSpan] = []
        self._enabled = True

    @contextmanager
    def span(
        self,
        name: str,
        input_data: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[TraceSpan, None, None]:
        """创建一个新的 Span。

        Args:
            name: Span 名称，如 ``agent.run`` / ``rag.retrieve``。
            input_data: 输入数据（会被截断记录）。
            metadata: 附加元数据。

        Yields:
            TraceSpan: 当前 Span 实例。
        """
        if not self._enabled:
            yield TraceSpan(name=name)  # dummy
            return

        span = TraceSpan(
            name=name,
            input_data=input_data,
            metadata=metadata or {},
        )

        # 挂到父 Span
        if self._stack:
            self._stack[-1].children.append(span)

        self._stack.append(span)

        try:
            yield span
        except Exception as e:
            span.error = str(e)
            raise
        finally:
            span.end_time = time.time()
            self._stack.pop()
            # 根 Span 结束时记录到历史
            if not self._stack:
                self._history.append(span)
                # 输出结构化日志
                logger.info(
                    "[Trace] %s — %.2fms | error=%s",
                    span.name,
                    span.duration_ms,
                    span.error,
                )

    def get_recent(self, n: int = 10) -> list[TraceSpan]:
        """获取最近 N 条根 Span。"""
        return list(self._history)[-n:]

    def get_stats(self) -> dict[str, Any]:
        """获取聚合统计。"""
        total = len(self._history)
        if not total:
            return {"total_calls": 0}
        durations = [s.duration_ms for s in self._history]
        errors = sum(1 for s in self._history if s.error)
        return {
            "total_calls": total,
            "avg_latency_ms": round(sum(durations) / total, 2),
            "max_latency_ms": round(max(durations), 2),
            "min_latency_ms": round(min(durations), 2),
            "error_count": errors,
            "error_rate": round(errors / total, 4),
        }

    def reset(self) -> None:
        """清空历史（用于测试）。"""
        self._history.clear()


# ------------------------------------------------------------------ #
# MetricsCollector —— 指标收集器
# ------------------------------------------------------------------ #


class MetricsCollector:
    """轻量级指标收集器。

    支持按名称和标签聚合，保留最近 N 条原始记录。
    """

    def __init__(self, max_history: int = 5000) -> None:
        self._data: defaultdict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=max_history)
        )

    def record(
        self,
        metric_name: str,
        value: float,
        tags: dict[str, Any] | None = None,
    ) -> None:
        """记录一条指标。"""
        self._data[metric_name].append(
            {
                "value": value,
                "timestamp": time.time(),
                "tags": tags or {},
            }
        )

    def get_summary(self, metric_name: str) -> dict[str, Any] | None:
        """获取指定指标的汇总统计。"""
        records = list(self._data.get(metric_name, []))
        if not records:
            return None
        values = [r["value"] for r in records]
        return {
            "count": len(values),
            "avg": round(sum(values) / len(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "latest": round(values[-1], 4),
        }

    def get_all(self) -> dict[str, dict[str, Any] | None]:
        """获取所有指标的汇总。"""
        return {k: self.get_summary(k) for k in self._data}

    def reset(self) -> None:
        """清空所有指标（用于测试）。"""
        self._data.clear()


# ------------------------------------------------------------------ #
# 全局单例与工厂
# ------------------------------------------------------------------ #

_tracer_instance: Tracer | None = None
_metrics_instance: MetricsCollector | None = None


def get_tracer() -> Tracer:
    """获取全局 Tracer 实例。"""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = Tracer()
    return _tracer_instance


def get_metrics() -> MetricsCollector:
    """获取全局 MetricsCollector 实例。"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = MetricsCollector()
    return _metrics_instance


def reset_observability() -> None:
    """重置全局可观测性实例（主要用于测试）。"""
    global _tracer_instance, _metrics_instance
    if _tracer_instance:
        _tracer_instance.reset()
    if _metrics_instance:
        _metrics_instance.reset()
