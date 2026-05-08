"""ModelFactory 单元测试。"""

import os
from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.models.factory import ModelFactory


class TestModelFactory:
    """测试模型工厂的注册、获取与列表功能。"""

    def setup_method(self) -> None:
        """每个测试前清空注册表，确保隔离。"""
        ModelFactory._llm_registry.clear()
        ModelFactory._embedding_registry.clear()
        ModelFactory._initialized = False

    # ------------------------------------------------------------------ #
    # LLM 注册与获取
    # ------------------------------------------------------------------ #
    def test_register_and_get_llm(self) -> None:
        mock_model = MagicMock()
        ModelFactory.register_llm("mock-model", lambda **kw: mock_model)

        result = ModelFactory.get_model("mock-model")
        assert result is mock_model

    def test_get_model_passes_kwargs(self) -> None:
        captured: dict = {}

        def constructor(**kw):
            captured.update(kw)
            return MagicMock()

        ModelFactory.register_llm("kw-model", constructor)
        ModelFactory.get_model("kw-model", temperature=0.5, max_tokens=100)

        assert captured["temperature"] == 0.5
        assert captured["max_tokens"] == 100

    def test_get_model_uses_default_from_settings(self) -> None:
        mock_model = MagicMock()
        ModelFactory.register_llm("default-test", lambda **kw: mock_model)

        with patch("comedy_agent.models.factory.settings") as mock_settings:
            mock_settings.default_model = "default-test"
            result = ModelFactory.get_model()

        assert result is mock_model

    def test_get_unknown_model_raises(self) -> None:
        with pytest.raises(ValueError, match="未知模型"):
            ModelFactory.get_model("non-existent-model")

    def test_list_models(self) -> None:
        ModelFactory.register_llm("model-a", lambda **kw: MagicMock())
        ModelFactory.register_llm("model-b", lambda **kw: MagicMock())

        names = ModelFactory.list_models()
        # _ensure_initialized() 会自动加载默认注册表，因此断言包含而非精确相等
        assert "model-a" in names
        assert "model-b" in names

    # ------------------------------------------------------------------ #
    # Embedding 注册与获取
    # ------------------------------------------------------------------ #
    def test_register_and_get_embedding(self) -> None:
        mock_emb = MagicMock()
        ModelFactory.register_embedding("mock-emb", lambda **kw: mock_emb)

        result = ModelFactory.get_embedding_model("mock-emb")
        assert result is mock_emb

    def test_get_embedding_uses_default_from_settings(self) -> None:
        mock_emb = MagicMock()
        ModelFactory.register_embedding("emb-default", lambda **kw: mock_emb)

        with patch("comedy_agent.models.factory.settings") as mock_settings:
            mock_settings.default_embedding_model = "emb-default"
            result = ModelFactory.get_embedding_model()

        assert result is mock_emb

    def test_get_unknown_embedding_raises(self) -> None:
        with pytest.raises(ValueError, match="未知 Embedding"):
            ModelFactory.get_embedding_model("non-existent-emb")

    def test_list_embedding_models(self) -> None:
        ModelFactory.register_embedding("emb-a", lambda **kw: MagicMock())
        ModelFactory.register_embedding("emb-b", lambda **kw: MagicMock())

        names = ModelFactory.list_embedding_models()
        # _ensure_initialized() 会自动加载默认注册表，因此断言包含而非精确相等
        assert "emb-a" in names
        assert "emb-b" in names

    # ------------------------------------------------------------------ #
    # Ollama 动态解析
    # ------------------------------------------------------------------ #
    @patch("comedy_agent.models.factory._HAS_OLLAMA", True)
    @patch("comedy_agent.models.factory.ChatOllama")
    def test_ollama_dynamic_fallback(self, mock_chat_ollama_cls) -> None:
        mock_instance = MagicMock()
        mock_chat_ollama_cls.return_value = mock_instance

        result = ModelFactory.get_model("ollama-mistral", temperature=0.7)

        mock_chat_ollama_cls.assert_called_once_with(
            model="mistral", temperature=0.7
        )
        assert result is mock_instance

    @patch("comedy_agent.models.factory._HAS_OLLAMA", False)
    def test_ollama_fallback_without_dependency_raises(self) -> None:
        with pytest.raises(ValueError, match="ollama"):
            ModelFactory.get_model("ollama-mistral")

    # ------------------------------------------------------------------ #
    # 内置注册表初始化
    # ------------------------------------------------------------------ #
    def test_default_registry_initialization(self) -> None:
        """确保默认注册表能正常初始化并包含常见模型。"""
        ModelFactory._ensure_initialized()
        models = ModelFactory.list_models()
        embeddings = ModelFactory.list_embedding_models()

        assert len(models) > 0 or len(embeddings) > 0
        # 至少应列出可用模型名称（具体取决于环境依赖是否安装）
