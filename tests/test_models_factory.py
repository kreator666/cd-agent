"""ModelFactory 单元测试。"""

import os
from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.models.factory import ModelConfigError, ModelFactory


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

    # ------------------------------------------------------------------ #
    # 配置错误
    # ------------------------------------------------------------------ #
    def test_model_config_error_message(self) -> None:
        """验证 ModelConfigError 携带清晰提示。"""
        err = ModelConfigError("test message")
        assert "test message" in str(err)

    # ------------------------------------------------------------------ #
    # 模型分层配置（任务类型绑定）
    # ------------------------------------------------------------------ #
    def test_get_model_by_task_type_creative(self) -> None:
        """creative 任务类型应返回配置的创意模型。"""
        mock_creative = MagicMock()
        ModelFactory.register_llm("test-creative", lambda **kw: mock_creative)
        with patch("comedy_agent.models.factory.settings.creative_model", "test-creative"):
            result = ModelFactory.get_model(task_type="creative")
        assert result is mock_creative

    def test_get_model_by_task_type_analytical(self) -> None:
        """analytical 任务类型应返回配置的分析模型。"""
        mock_analytical = MagicMock()
        ModelFactory.register_llm("test-analytical", lambda **kw: mock_analytical)
        with patch("comedy_agent.models.factory.settings.analytical_model", "test-analytical"):
            result = ModelFactory.get_model(task_type="analytical")
        assert result is mock_analytical

    def test_get_model_by_task_type_fast(self) -> None:
        """fast 任务类型应返回配置的轻量模型。"""
        mock_fast = MagicMock()
        ModelFactory.register_llm("test-fast", lambda **kw: mock_fast)
        with patch("comedy_agent.models.factory.settings.fast_model", "test-fast"):
            result = ModelFactory.get_model(task_type="fast")
        assert result is mock_fast

    def test_get_model_name_overrides_task_type(self) -> None:
        """显式传入 name 时，task_type 应被忽略。"""
        mock_named = MagicMock()
        ModelFactory.register_llm("named-model", lambda **kw: mock_named)
        result = ModelFactory.get_model(name="named-model", task_type="creative")
        assert result is mock_named

    def test_get_model_unknown_task_type_fallback(self) -> None:
        """未知 task_type 应回退到默认模型。"""
        mock_default = MagicMock()
        ModelFactory.register_llm("default-model", lambda **kw: mock_default)
        with patch("comedy_agent.models.factory.settings.default_model", "default-model"):
            result = ModelFactory.get_model(task_type="unknown")
        assert result is mock_default

    # ------------------------------------------------------------------ #
    # 自动 Fallback
    # ------------------------------------------------------------------ #
    def test_get_model_with_fallback_returns_runnable(self) -> None:
        """get_model_with_fallback 应返回 RunnableWithFallbacks 实例。"""
        from langchain_core.runnables import RunnableLambda, RunnableWithFallbacks

        ModelFactory.register_llm("primary-m", lambda **kw: RunnableLambda(lambda x: "primary"))
        ModelFactory.register_llm("fb-m", lambda **kw: RunnableLambda(lambda x: "fallback"))
        with patch("comedy_agent.models.factory.settings.creative_model", "primary-m"), \
             patch("comedy_agent.models.factory.settings.creative_fallback_models", "fb-m"):
            result = ModelFactory.get_model_with_fallback(task_type="creative")
        assert isinstance(result, RunnableWithFallbacks)

    def test_get_model_with_fallback_empty_fallbacks(self) -> None:
        """备用模型链为空时，只返回主模型包装。"""
        from langchain_core.runnables import RunnableLambda, RunnableWithFallbacks

        ModelFactory.register_llm("solo-m", lambda **kw: RunnableLambda(lambda x: "solo"))
        with patch("comedy_agent.models.factory.settings.creative_model", "solo-m"), \
             patch("comedy_agent.models.factory.settings.creative_fallback_models", ""):
            result = ModelFactory.get_model_with_fallback(task_type="creative")
        assert isinstance(result, RunnableWithFallbacks)

    def test_get_model_with_fallback_ignores_unavailable_fallback(self) -> None:
        """不可用的备用模型应被跳过，不阻断主模型返回。"""
        from langchain_core.runnables import RunnableLambda, RunnableWithFallbacks

        ModelFactory.register_llm("good-m", lambda **kw: RunnableLambda(lambda x: "good"))
        with patch("comedy_agent.models.factory.settings.creative_model", "good-m"), \
             patch("comedy_agent.models.factory.settings.creative_fallback_models", "non-existent-model"):
            result = ModelFactory.get_model_with_fallback(task_type="creative")
        assert isinstance(result, RunnableWithFallbacks)
