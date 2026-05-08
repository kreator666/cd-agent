"""ModelFactory —— 统一封装 OpenAI / Anthropic / Ollama / 通义千问等模型接口。

预留接口，将在任务 1.2 中实现。
"""

from typing import Any

from langchain_core.language_models.base import BaseLanguageModel


class ModelFactory:
    """模型工厂：根据配置返回对应的 LLM 实例。"""

    _registry: dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, constructor: Any) -> None:
        """注册模型构造器。"""
        cls._registry[name] = constructor

    @classmethod
    def get_model(cls, name: str | None = None, **kwargs: Any) -> BaseLanguageModel:
        """获取指定名称的模型实例。

        Args:
            name: 模型标识，如 "gpt-4o", "claude-3-5-sonnet" 等。
            **kwargs: 额外参数传递给模型构造器。

        Returns:
            BaseLanguageModel: LangChain 兼容的 LLM 实例。
        """
        raise NotImplementedError("将在任务 1.2 中实现。")
