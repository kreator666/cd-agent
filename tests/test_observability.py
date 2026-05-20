"""可观测性模块测试 —— 调用链追踪、指标收集与 LangSmith 配置。"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from comedy_agent.core.observability import (
    MetricsCollector,
    TraceSpan,
    Tracer,
    get_metrics,
    get_tracer,
    reset_observability,
    setup_langsmith,
)


# ------------------------------------------------------------------ #
# TraceSpan
# ------------------------------------------------------------------ #
class TestTraceSpan:
    def test_duration_ms_basic(self):
        span = TraceSpan(name="test")
        span.end_time = span.start_time + 0.5  # 500ms
        assert span.duration_ms == 500.0

    def test_duration_ms_auto_when_not_ended(self):
        span = TraceSpan(name="test")
        # end_time 为 None 时，duration_ms 使用当前时间
        assert span.duration_ms >= 0.0

    def test_to_dict_truncate(self):
        span = TraceSpan(name="test", input_data="x" * 300, metadata={"k": "v"})
        d = span.to_dict()
        assert d["name"] == "test"
        assert d["input"].endswith("...")
        assert len(d["input"]) <= 203


# ------------------------------------------------------------------ #
# Tracer
# ------------------------------------------------------------------ #
class TestTracer:
    def test_span_records_to_history(self):
        tracer = Tracer()
        with tracer.span("op", input_data="hello") as span:
            span.output_data = "world"
        assert len(tracer.get_recent(n=1)) == 1

    def test_span_nested_structure(self):
        tracer = Tracer()
        with tracer.span("parent"):
            with tracer.span("child"):
                pass
        root = tracer.get_recent(n=1)[0]
        assert root.name == "parent"
        assert len(root.children) == 1
        assert root.children[0].name == "child"

    def test_span_error_captured(self):
        tracer = Tracer()
        with pytest.raises(RuntimeError, match="boom"):
            with tracer.span("fail"):
                raise RuntimeError("boom")
        root = tracer.get_recent(n=1)[0]
        assert root.error == "boom"

    def test_stats(self):
        tracer = Tracer()
        assert tracer.get_stats() == {"total_calls": 0}

        # 手动创建根 Span 并直接推入历史，避免上下文管理器覆盖 end_time
        s1 = TraceSpan(name="fast")
        s1.end_time = s1.start_time + 0.01
        s2 = TraceSpan(name="slow")
        s2.end_time = s2.start_time + 0.05
        tracer._history.append(s1)
        tracer._history.append(s2)

        stats = tracer.get_stats()
        assert stats["total_calls"] == 2
        assert stats["error_count"] == 0
        assert stats["error_rate"] == 0.0
        assert stats["avg_latency_ms"] >= 10.0

    def test_disabled_tracer(self):
        tracer = Tracer()
        tracer._enabled = False
        with tracer.span("noop"):
            pass
        assert len(tracer.get_recent(n=1)) == 0


# ------------------------------------------------------------------ #
# MetricsCollector
# ------------------------------------------------------------------ #
class TestMetricsCollector:
    def test_record_and_summary(self):
        mc = MetricsCollector()
        mc.record("latency", 100, tags={"model": "gpt-4o"})
        mc.record("latency", 200, tags={"model": "gpt-4o"})
        summary = mc.get_summary("latency")
        assert summary is not None
        assert summary["count"] == 2
        assert summary["avg"] == 150.0
        assert summary["min"] == 100.0
        assert summary["max"] == 200.0
        assert summary["latest"] == 200.0

    def test_get_all_empty(self):
        mc = MetricsCollector()
        assert mc.get_all() == {}

    def test_reset(self):
        mc = MetricsCollector()
        mc.record("x", 1)
        mc.reset()
        assert mc.get_summary("x") is None


# ------------------------------------------------------------------ #
# setup_langsmith
# ------------------------------------------------------------------ #
class TestSetupLangSmith:
    def test_setup_with_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("comedy_agent.core.observability.settings") as mock_settings:
                mock_settings.langsmith_api_key = "ls-test-key"
                mock_settings.langsmith_project = "test-project"
                ok = setup_langsmith()
                assert ok is True
                assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
                assert os.environ.get("LANGCHAIN_API_KEY") == "ls-test-key"
                assert os.environ.get("LANGCHAIN_PROJECT") == "test-project"

    def test_setup_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("comedy_agent.core.observability.settings") as mock_settings:
                mock_settings.langsmith_api_key = ""
                mock_settings.langsmith_project = "default"
                ok = setup_langsmith()
                assert ok is False
                assert os.environ.get("LANGCHAIN_TRACING_V2") is None


# ------------------------------------------------------------------ #
# 全局单例
# ------------------------------------------------------------------ #
class TestGlobalInstances:
    def test_get_tracer_singleton(self):
        t1 = get_tracer()
        t2 = get_tracer()
        assert t1 is t2

    def test_get_metrics_singleton(self):
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_reset_observability(self):
        tracer = get_tracer()
        metrics = get_metrics()
        with tracer.span("x"):
            pass
        metrics.record("x", 1)
        reset_observability()
        assert len(tracer.get_recent(n=1)) == 0
        assert metrics.get_summary("x") is None
