"""模型调用 Token 用量追踪。

通过 LangChain Callback 在每次 LLM 调用结束时捕获 usage，
并将累计用量写入 contextvars，供外层 API 读取后计费。
"""

from __future__ import annotations

import contextvars
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


@dataclass
class ModelUsage:
    """单次或累计的模型 Token 用量。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str | None = None

    def merge(self, other: "ModelUsage") -> "ModelUsage":
        """合并两次用量。"""
        return ModelUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            model=self.model or other.model,
        )


# 当前请求上下文中累计的模型用量
_model_usage_context: contextvars.ContextVar[list[ModelUsage] | None] = contextvars.ContextVar(
    "model_usage_context", default=None
)


def reset_model_usage() -> None:
    """重置当前上下文的用量累计。"""
    _model_usage_context.set([])


def get_model_usage() -> ModelUsage | None:
    """获取当前上下文累计用量；若无记录返回 None。"""
    usages = _model_usage_context.get()
    if not usages:
        return None
    total = usages[0]
    for u in usages[1:]:
        total = total.merge(u)
    return total


def _extract_usage_from_response(response: LLMResult, model_name: str | None = None) -> ModelUsage:
    """从 LLMResult 中提取 Token 用量，支持多种 provider 格式。"""
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    # 1. 尝试从 response.llm_output["token_usage"] 读取（OpenAI 兼容格式）
    llm_output = getattr(response, "llm_output", {}) or {}
    token_usage = llm_output.get("token_usage") if isinstance(llm_output, dict) else None
    if token_usage:
        prompt_tokens = token_usage.get("prompt_tokens") or token_usage.get("input_tokens") or 0
        completion_tokens = token_usage.get("completion_tokens") or token_usage.get("output_tokens") or 0
        total_tokens = token_usage.get("total_tokens") or (prompt_tokens + completion_tokens)

    # 2. 尝试从每个 generation 的 message.usage_metadata 读取（LangChain 标准字段）
    if total_tokens == 0:
        for gens in response.generations:
            for gen in gens:
                msg = getattr(gen, "message", None)
                if msg is None:
                    continue
                usage = getattr(msg, "usage_metadata", None) or {}
                if usage:
                    prompt_tokens = max(prompt_tokens, usage.get("input_tokens", 0))
                    completion_tokens = max(completion_tokens, usage.get("output_tokens", 0))
                    total_tokens = max(total_tokens, usage.get("total_tokens", 0))

    # 3. Ollama 等本地模型可能把计数放在 response_metadata
    if total_tokens == 0:
        for gens in response.generations:
            for gen in gens:
                msg = getattr(gen, "message", None)
                if msg is None:
                    continue
                meta = getattr(msg, "response_metadata", {}) or {}
                if isinstance(meta, dict):
                    prompt_tokens = prompt_tokens or meta.get("prompt_eval_count", 0)
                    completion_tokens = completion_tokens or meta.get("eval_count", 0)
                    total_tokens = total_tokens or (
                        prompt_tokens + completion_tokens
                        or meta.get("total_duration")
                    )

    # 兜底：如果只有 total_tokens，按 6:4 拆分（仅用于展示，不影响扣费）
    if total_tokens == 0 and (prompt_tokens or completion_tokens):
        total_tokens = prompt_tokens + completion_tokens
    elif prompt_tokens == 0 and completion_tokens == 0 and total_tokens > 0:
        prompt_tokens = int(total_tokens * 0.6)
        completion_tokens = total_tokens - prompt_tokens

    return ModelUsage(
        prompt_tokens=int(prompt_tokens or 0),
        completion_tokens=int(completion_tokens or 0),
        total_tokens=int(total_tokens or 0),
        model=model_name,
    )


class UsageCallbackHandler(BaseCallbackHandler):
    """捕获 LLM 调用 Token 用量的 Callback。"""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name
        super().__init__()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM 调用结束时提取 usage 并累计到上下文。"""
        try:
            usage = _extract_usage_from_response(response, model_name=self.model_name)
            if usage.total_tokens <= 0:
                return

            usages = _model_usage_context.get()
            if usages is None:
                usages = []
                _model_usage_context.set(usages)
            usages.append(usage)
            logger.debug(
                "Captured usage for %s: prompt=%d completion=%d total=%d",
                self.model_name,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
            )
        except Exception:
            logger.warning("Failed to extract model usage", exc_info=True)


def _estimate_tokens(text: str) -> int:
    """启发式估算 Token 数（与项目其他模块保持一致）。"""
    zh_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other_chars = len(text) - zh_chars
    return int(zh_chars * 1.5 + other_chars * 0.25 + 0.5)


def estimate_usage_from_text(prompt: str, completion: str, model_name: str | None = None) -> ModelUsage:
    """当模型不返回 usage 时，按文本长度启发式估算。"""
    return ModelUsage(
        prompt_tokens=_estimate_tokens(prompt),
        completion_tokens=_estimate_tokens(completion),
        total_tokens=_estimate_tokens(prompt) + _estimate_tokens(completion),
        model=model_name,
    )
