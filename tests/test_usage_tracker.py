"""usage_tracker 模块单元测试。"""

from __future__ import annotations

import pytest
from langchain_core.outputs import Generation, LLMResult

from comedy_agent.models.usage_tracker import (
    ModelUsage,
    UsageCallbackHandler,
    _extract_usage_from_response,
    get_model_usage,
    reset_model_usage,
)


class TestExtractUsageFromResponse:
    """测试从 LLMResult 中提取 token 用量。"""

    def test_extract_with_none_total_tokens(self) -> None:
        """llm_output 中 total_tokens 为 None 时不应抛 TypeError。"""
        result = LLMResult(
            generations=[[Generation(text="hi")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": None,
                }
            },
        )
        usage = _extract_usage_from_response(result)
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 5
        assert usage.total_tokens == 15

    def test_extract_with_none_prompt_and_completion(self) -> None:
        """llm_output 中 prompt/completion 为 None，仅有 total_tokens 时，按 6:4 拆分。"""
        result = LLMResult(
            generations=[[Generation(text="hi")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": 100,
                }
            },
        )
        usage = _extract_usage_from_response(result)
        assert usage.prompt_tokens == 60
        assert usage.completion_tokens == 40
        assert usage.total_tokens == 100

    def test_extract_with_string_numbers(self) -> None:
        """字符串数字应被安全转换为整数。"""
        result = LLMResult(
            generations=[[Generation(text="hi")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": "12",
                    "completion_tokens": "8",
                    "total_tokens": "20",
                }
            },
        )
        usage = _extract_usage_from_response(result)
        assert usage.prompt_tokens == 12
        assert usage.completion_tokens == 8
        assert usage.total_tokens == 20

    def test_extract_with_invalid_values(self) -> None:
        """非法非数字值应被当作 0 处理。"""
        result = LLMResult(
            generations=[[Generation(text="hi")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": "abc",
                    "completion_tokens": None,
                    "total_tokens": {},
                }
            },
        )
        usage = _extract_usage_from_response(result)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_extract_empty_response(self) -> None:
        """空响应应返回 0 用量。"""
        result = LLMResult(generations=[[Generation(text="hi")]])
        usage = _extract_usage_from_response(result)
        assert usage.total_tokens == 0


class TestUsageCallbackHandler:
    """测试 UsageCallbackHandler 累计用量到上下文。"""

    def test_callback_accumulates_usage(self) -> None:
        reset_model_usage()
        handler = UsageCallbackHandler(model_name="gpt-4o")
        result = LLMResult(
            generations=[[Generation(text="hello")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                }
            },
        )
        handler.on_llm_end(result)

        total = get_model_usage()
        assert total is not None
        assert total.prompt_tokens == 10
        assert total.completion_tokens == 5
        assert total.total_tokens == 15
        assert total.model == "gpt-4o"

    def test_callback_with_none_usage_does_not_crash(self) -> None:
        """usage 字段为 None 时回调不应崩溃。"""
        reset_model_usage()
        handler = UsageCallbackHandler(model_name="gpt-4o")
        result = LLMResult(
            generations=[[Generation(text="hello")]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                }
            },
        )
        # 不应抛出异常
        handler.on_llm_end(result)
        total = get_model_usage()
        assert total is None


class TestModelUsage:
    """测试 ModelUsage 数据类。"""

    def test_merge(self) -> None:
        u1 = ModelUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        u2 = ModelUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30)
        merged = u1.merge(u2)
        assert merged.prompt_tokens == 30
        assert merged.completion_tokens == 15
        assert merged.total_tokens == 45
