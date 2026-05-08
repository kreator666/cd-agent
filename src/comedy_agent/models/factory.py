"""ModelFactory —— 统一封装 OpenAI / Anthropic / Ollama / 通义千问等模型接口。

支持配置化模型切换与运行时参数覆盖。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.core.config import settings

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
    from langchain_community.chat_models import ChatOllama

    _HAS_OLLAMA = True
except ImportError:
    _HAS_OLLAMA = False
    logger.warning("langchain-community 未安装，Ollama 模型不可用")

try:
    from langchain_community.chat_models.tongyi import ChatTongyi

    _HAS_TONGYI = True
except ImportError:
    _HAS_TONGYI = False
    logger.warning("langchain-community 未安装，通义千问模型不可用")


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
            cls.register_llm(
                "gpt-4o",
                lambda **kw: ChatOpenAI(
                    model="gpt-4o",
                    api_key=settings.openai_api_key or None,
                    **kw,
                ),
            )
            cls.register_llm(
                "gpt-4o-mini",
                lambda **kw: ChatOpenAI(
                    model="gpt-4o-mini",
                    api_key=settings.openai_api_key or None,
                    **kw,
                ),
            )
            cls.register_llm(
                "gpt-4-turbo",
                lambda **kw: ChatOpenAI(
                    model="gpt-4-turbo",
                    api_key=settings.openai_api_key or None,
                    **kw,
                ),
            )

        # Anthropic
        if _HAS_ANTHROPIC:
            cls.register_llm(
                "claude-3-5-sonnet",
                lambda **kw: ChatAnthropic(
                    model="claude-3-5-sonnet-20241022",
                    api_key=settings.anthropic_api_key or None,
                    **kw,
                ),
            )
            cls.register_llm(
                "claude-3-opus",
                lambda **kw: ChatAnthropic(
                    model="claude-3-opus-20240229",
                    api_key=settings.anthropic_api_key or None,
                    **kw,
                ),
            )
            cls.register_llm(
                "claude-3-5-haiku",
                lambda **kw: ChatAnthropic(
                    model="claude-3-5-haiku-20241022",
                    api_key=settings.anthropic_api_key or None,
                    **kw,
                ),
            )

        # 通义千问 (Tongyi / DashScope)
        if _HAS_TONGYI:
            cls.register_llm(
                "qwen-max",
                lambda **kw: ChatTongyi(
                    model="qwen-max",
                    dashscope_api_key=settings.qwen_api_key or None,
                    **kw,
                ),
            )
            cls.register_llm(
                "qwen-plus",
                lambda **kw: ChatTongyi(
                    model="qwen-plus",
                    dashscope_api_key=settings.qwen_api_key or None,
                    **kw,
                ),
            )
            cls.register_llm(
                "qwen-turbo",
                lambda **kw: ChatTongyi(
                    model="qwen-turbo",
                    dashscope_api_key=settings.qwen_api_key or None,
                    **kw,
                ),
            )

        # Ollama（本地模型，无 API Key 要求）
        if _HAS_OLLAMA:
            cls.register_llm(
                "ollama-llama3",
                lambda **kw: ChatOllama(model="llama3", **kw),
            )
            cls.register_llm(
                "ollama-qwen2.5",
                lambda **kw: ChatOllama(model="qwen2.5", **kw),
            )
            cls.register_llm(
                "ollama-llama3.1",
                lambda **kw: ChatOllama(model="llama3.1", **kw),
            )

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

    @classmethod
    def get_model(cls, name: str | None = None, **kwargs: Any) -> BaseChatModel:
        """获取指定名称的 ChatModel 实例。

        Args:
            name: 模型标识，如 ``gpt-4o``、``claude-3-5-sonnet`` 等。
                为 ``None`` 时使用 ``settings.default_model``。
            **kwargs: 额外参数传递给模型构造器（如 ``temperature``、``max_tokens``）。

        Returns:
            BaseChatModel: LangChain 兼容的聊天模型实例。

        Raises:
            ValueError: 模型名称未注册且无法动态解析。
        """
        cls._ensure_initialized()
        name = name or settings.default_model

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
