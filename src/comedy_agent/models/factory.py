"""ModelFactory —— 统一封装 OpenAI / Anthropic / Ollama / 通义千问等模型接口。

支持配置化模型切换与运行时参数覆盖。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import httpx
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.core.config import settings
from comedy_agent.core.observability import get_metrics

logger = logging.getLogger(__name__)

# 延迟导入：可选依赖缺失时不阻断工厂加载
try:
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False
    logger.warning("langchain-openai 未安装，OpenAI 模型不可用")

try:
    from langchain_anthropic import ChatAnthropic

    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False
    logger.warning("langchain-anthropic 未安装，Anthropic 模型不可用")

try:
    from langchain_ollama import ChatOllama

    _HAS_OLLAMA = True
except ImportError:
    try:
        # 兼容旧版导入
        from langchain_community.chat_models import ChatOllama

        _HAS_OLLAMA = True
        logger.warning(
            "langchain_ollama 未安装，使用已弃用的 langchain_community.ChatOllama。"
            "建议运行：pip install langchain-ollama"
        )
    except ImportError:
        _HAS_OLLAMA = False
        logger.warning("langchain-ollama 未安装，Ollama 模型不可用")

try:
    from langchain_community.chat_models.tongyi import ChatTongyi

    _HAS_TONGYI = True
except ImportError:
    _HAS_TONGYI = False
    logger.warning("langchain-community 未安装，通义千问模型不可用")


class ModelConfigError(Exception):
    """模型配置错误（如 API Key 缺失）。"""


class ModelFactory:
    """模型工厂：根据配置返回对应的 LLM / Embedding 实例。"""

    _llm_registry: dict[str, Callable[..., BaseChatModel]] = {}
    _embedding_registry: dict[str, Callable[..., Embeddings]] = {}
    _initialized: bool = False

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #
    @classmethod
    def _ensure_initialized(cls) -> None:
        if cls._initialized:
            return
        cls._build_default_llm_registry()
        cls._build_default_embedding_registry()
        cls._initialized = True

    @classmethod
    def _build_default_llm_registry(cls) -> None:
        """注册内置 LLM 构造器。"""
        # OpenAI
        if _HAS_OPENAI:
            def _openai(model: str, **kw):
                key = settings.openai_api_key
                if not key:
                    raise ModelConfigError(
                        f"模型 '{model}' 需要 OpenAI API Key。\n"
                        f"请设置环境变量：export OPENAI_API_KEY=sk-xxx\n"
                        f"或使用本地模型：--model ollama-llama3"
                    )
                return ChatOpenAI(model=model, api_key=key, **kw)

            cls.register_llm("gpt-4o", lambda **kw: _openai("gpt-4o", **kw))
            cls.register_llm("gpt-4o-mini", lambda **kw: _openai("gpt-4o-mini", **kw))
            cls.register_llm("gpt-4-turbo", lambda **kw: _openai("gpt-4-turbo", **kw))

        # Anthropic
        if _HAS_ANTHROPIC:
            def _anthropic(model: str, **kw):
                key = settings.anthropic_api_key
                if not key:
                    raise ModelConfigError(
                        f"模型 '{model}' 需要 Anthropic API Key。\n"
                        f"请设置环境变量：export ANTHROPIC_API_KEY=sk-ant-xxx\n"
                        f"或使用本地模型：--model ollama-llama3"
                    )
                return ChatAnthropic(model=model, api_key=key, **kw)

            cls.register_llm(
                "claude-3-5-sonnet", lambda **kw: _anthropic("claude-3-5-sonnet-20241022", **kw)
            )
            cls.register_llm(
                "claude-3-5-sonnet-20241022",
                lambda **kw: _anthropic("claude-3-5-sonnet-20241022", **kw),
            )
            cls.register_llm(
                "claude-3-opus", lambda **kw: _anthropic("claude-3-opus-20240229", **kw)
            )
            cls.register_llm(
                "claude-3-opus-20240229",
                lambda **kw: _anthropic("claude-3-opus-20240229", **kw),
            )
            cls.register_llm(
                "claude-3-5-haiku", lambda **kw: _anthropic("claude-3-5-haiku-20241022", **kw)
            )
            cls.register_llm(
                "claude-3-5-haiku-20241022",
                lambda **kw: _anthropic("claude-3-5-haiku-20241022", **kw),
            )

        # 通义千问 (Tongyi / DashScope)
        if _HAS_TONGYI:
            def _tongyi(model: str, **kw):
                key = settings.qwen_api_key
                if not key:
                    raise ModelConfigError(
                        f"模型 '{model}' 需要 DashScope API Key。\n"
                        f"请设置环境变量：export DASHSCOPE_API_KEY=sk-xxx\n"
                        f"或使用本地模型：--model ollama-llama3"
                    )
                return ChatTongyi(model=model, dashscope_api_key=key, **kw)

            cls.register_llm("qwen-max", lambda **kw: _tongyi("qwen-max", **kw))
            cls.register_llm("qwen-plus", lambda **kw: _tongyi("qwen-plus", **kw))
            cls.register_llm("qwen-turbo", lambda **kw: _tongyi("qwen-turbo", **kw))

        # Ollama（本地模型，无 API Key 要求）
        # 使用自定义 HTTPTransport 避免 Windows 系统代理干扰
        if _HAS_OLLAMA:
            _ollama_transport = httpx.HTTPTransport(retries=1)
            _ollama_kwargs = {
                "base_url": "http://localhost:11434",
                "client_kwargs": {"transport": _ollama_transport},
            }
            cls.register_llm(
                "ollama-llama3",
                lambda **kw: ChatOllama(model="llama3", **_ollama_kwargs, **kw),
            )
            cls.register_llm(
                "ollama-qwen2.5",
                lambda **kw: ChatOllama(model="qwen2.5", **_ollama_kwargs, **kw),
            )
            cls.register_llm(
                "ollama-llama3.1",
                lambda **kw: ChatOllama(model="llama3.1", **_ollama_kwargs, **kw),
            )

        # Moonshot / Kimi（OpenAI 兼容接口）
        if _HAS_OPENAI:
            def _kimi(model: str, **kw):
                key = settings.moonshot_api_key
                if not key:
                    raise ModelConfigError(
                        f"模型 '{model}' 需要 Moonshot API Key。\n"
                        f"请设置环境变量：export MOONSHOT_API_KEY=sk-kimi-xxx\n"
                        f"或使用其他模型：--model gpt-4o / claude-3-5-sonnet"
                    )
                return ChatOpenAI(
                    model=model,
                    api_key=key,
                    base_url="https://api.moonshot.cn/v1",
                    **kw,
                )

            cls.register_llm("kimi-for-coding", lambda **kw: _kimi("kimi-for-coding", **kw))
            cls.register_llm("kimi-code", lambda **kw: _kimi("kimi-for-coding", **kw))

    @classmethod
    def _build_default_embedding_registry(cls) -> None:
        """注册内置 Embedding 构造器。"""
        if _HAS_OPENAI:
            cls.register_embedding(
                "text-embedding-3-large",
                lambda **kw: OpenAIEmbeddings(
                    model="text-embedding-3-large",
                    api_key=settings.openai_api_key or None,
                    **kw,
                ),
            )
            cls.register_embedding(
                "text-embedding-3-small",
                lambda **kw: OpenAIEmbeddings(
                    model="text-embedding-3-small",
                    api_key=settings.openai_api_key or None,
                    **kw,
                ),
            )

        # 本地 HuggingFace Embedding（无需 API Key，适合离线环境）
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings

            cls.register_embedding(
                "hf-local",
                lambda **kw: HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2",
                    **kw,
                ),
            )
        except ImportError:
            pass

    # ------------------------------------------------------------------ #
    # 公共 API
    # ------------------------------------------------------------------ #
    @classmethod
    def register_llm(
        cls, name: str, constructor: Callable[..., BaseChatModel]
    ) -> None:
        """注册 LLM 构造器。"""
        cls._llm_registry[name] = constructor

    @classmethod
    def register_embedding(
        cls, name: str, constructor: Callable[..., Embeddings]
    ) -> None:
        """注册 Embedding 构造器。"""
        cls._embedding_registry[name] = constructor

    _TASK_TYPE_MAP: dict[str, str] = {
        "creative": "creative_model",
        "analytical": "analytical_model",
        "fast": "fast_model",
    }

    @classmethod
    def get_model(
        cls,
        name: str | None = None,
        task_type: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        """获取指定名称或任务类型的 ChatModel 实例。

        Args:
            name: 模型标识，如 ``gpt-4o``、``claude-3-5-sonnet`` 等。
                为 ``None`` 时，若 ``task_type`` 提供则按任务类型绑定模型，
                否则使用 ``settings.default_model``。
            task_type: 任务类型，可选 ``creative`` / ``analytical`` / ``fast``。
            **kwargs: 额外参数传递给模型构造器（如 ``temperature``、``max_tokens``）。

        Returns:
            BaseChatModel: LangChain 兼容的聊天模型实例。

        Raises:
            ValueError: 模型名称未注册且无法动态解析。
        """
        cls._ensure_initialized()

        if name is None and task_type is not None:
            attr = cls._TASK_TYPE_MAP.get(task_type)
            if attr:
                name = getattr(settings, attr, settings.default_model)
                logger.debug("Task type '%s' -> model '%s'", task_type, name)
            else:
                logger.warning("未知 task_type '%s'，使用默认模型", task_type)

        name = name or settings.default_model

        # 记录模型使用指标
        metrics = get_metrics()
        metrics.record("model.calls", 1, tags={"model": name, "task_type": task_type or "none"})

        if name in cls._llm_registry:
            return cls._llm_registry[name](**kwargs)

        # 兜底：Ollama 支持任意本地模型名
        if name.startswith("ollama-"):
            if not _HAS_OLLAMA:
                raise ValueError(
                    f"模型 '{name}' 需要 ollama 支持，但 langchain-community 未安装"
                )
            model_id = name.replace("ollama-", "")
            return ChatOllama(model=model_id, **kwargs)

        raise ValueError(
            f"未知模型 '{name}'。可用模型: {cls.list_models()}"
        )

    @classmethod
    def get_model_with_fallback(
        cls,
        name: str | None = None,
        task_type: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """获取带自动 Fallback 的模型实例。

        主模型失败（超时/限流/异常）时，自动降级到备用模型链。

        Args:
            name: 主模型标识，为 ``None`` 时按 ``task_type`` 解析。
            task_type: 任务类型，用于解析主模型和备用模型链。
            **kwargs: 额外参数传递给模型构造器。

        Returns:
            RunnableWithFallbacks: 包装了主模型与备用模型链的 Runnable。
        """
        from langchain_core.runnables import RunnableWithFallbacks

        primary = cls.get_model(name=name, task_type=task_type, **kwargs)

        # 解析备用模型链
        fallback_names: list[str] = []
        if task_type:
            attr = f"{task_type}_fallback_models"
            fallback_str = getattr(settings, attr, "")
            if fallback_str:
                fallback_names = [
                    n.strip() for n in fallback_str.split(",") if n.strip()
                ]

        fallbacks: list[Any] = []
        for fb_name in fallback_names:
            try:
                fallbacks.append(cls.get_model(name=fb_name, **kwargs))
            except Exception as e:
                logger.warning(
                    "Fallback model '%s' unavailable: %s", fb_name, e
                )

        exceptions = (
            Exception,
        )  # 可根据需要细化：ConnectionError, TimeoutError, RateLimitError 等

        metrics = get_metrics()
        metrics.record(
            "model.fallback_chain",
            1,
            tags={
                "primary": name or settings.default_model,
                "fallbacks": ",".join(fallback_names) if fallback_names else "none",
            },
        )

        return RunnableWithFallbacks(
            runnable=primary,
            fallbacks=fallbacks,
            exceptions_to_handle=exceptions,
        )

    @classmethod
    def get_embedding_model(
        cls, name: str | None = None, **kwargs: Any
    ) -> Embeddings:
        """获取指定名称的 Embedding 模型实例。

        Args:
            name: 模型标识，如 ``text-embedding-3-large``。
                为 ``None`` 时使用 ``settings.default_embedding_model``。
            **kwargs: 额外参数传递给构造器。

        Returns:
            Embeddings: LangChain 兼容的嵌入模型实例。
        """
        cls._ensure_initialized()
        name = name or settings.default_embedding_model

        if name in cls._embedding_registry:
            return cls._embedding_registry[name](**kwargs)

        raise ValueError(
            f"未知 Embedding 模型 '{name}'。可用模型: {cls.list_embedding_models()}"
        )

    @classmethod
    def list_models(cls) -> list[str]:
        """返回所有已注册的 LLM 名称列表。"""
        cls._ensure_initialized()
        return sorted(cls._llm_registry.keys())

    @classmethod
    def list_embedding_models(cls) -> list[str]:
        """返回所有已注册的 Embedding 模型名称列表。"""
        cls._ensure_initialized()
        return sorted(cls._embedding_registry.keys())

    @classmethod
    def list_available_models(cls) -> list[str]:
        """返回当前环境实际可用的模型名称列表。

        根据已配置的 API Key 和本地 Ollama 模型动态检测。
        """
        cls._ensure_initialized()
        available: list[str] = []

        # 云端模型：检查对应 API Key
        key_checks = {
            "gpt-4o": settings.openai_api_key,
            "gpt-4o-mini": settings.openai_api_key,
            "gpt-4-turbo": settings.openai_api_key,
            "claude-3-5-sonnet": settings.anthropic_api_key,
            "claude-3-opus": settings.anthropic_api_key,
            "claude-3-5-haiku": settings.anthropic_api_key,
            "qwen-max": settings.qwen_api_key,
            "qwen-plus": settings.qwen_api_key,
            "qwen-turbo": settings.qwen_api_key,
            "kimi-for-coding": settings.moonshot_api_key,
            "kimi-code": settings.moonshot_api_key,
        }
        for name, key in key_checks.items():
            if key and name in cls._llm_registry:
                available.append(name)

        # Ollama 本地模型：探测服务（使用 httpx 并禁用代理，避免系统代理干扰）
        if _HAS_OLLAMA:
            try:
                import json

                import httpx

                transport = httpx.HTTPTransport(retries=1)
                with httpx.Client(transport=transport, proxy=None, timeout=3) as client:
                    resp = client.get("http://localhost:11434/api/tags")
                    resp.raise_for_status()
                    data = resp.json()
                    for m in data.get("models", []):
                        local_name = m.get("name", "")
                        mapped = cls._map_ollama_name(local_name)
                        if mapped and mapped not in available:
                            available.append(mapped)
            except Exception:
                pass  # Ollama 未运行，静默跳过

        return sorted(available)

    @staticmethod
    def _map_ollama_name(ollama_name: str) -> str | None:
        """将 Ollama 本地模型名映射为 factory 注册名。"""
        name_lower = ollama_name.lower()
        mapping = {
            "llama3": "ollama-llama3",
            "llama3:latest": "ollama-llama3",
            "llama3.1": "ollama-llama3.1",
            "llama3.1:latest": "ollama-llama3.1",
            "qwen2.5": "ollama-qwen2.5",
            "qwen2.5:latest": "ollama-qwen2.5",
            "qwen2.5:7b": "ollama-qwen2.5",
        }
        return mapping.get(name_lower)
