"""PromptManager 单元测试。"""

import tempfile
from pathlib import Path

import pytest

from comedy_agent.core.prompt_manager import PromptManager, PromptNotFoundError


class TestPromptManager:
    """测试 Prompt 管理器的注册、加载、渲染与 A/B 测试。"""

    def setup_method(self) -> None:
        """每个测试前清空单例状态。"""
        pm = PromptManager()
        pm._store.clear()

    # ------------------------------------------------------------------ #
    # 注册与查询
    # ------------------------------------------------------------------ #
    def test_register_and_get(self):
        pm = PromptManager()
        pm.register("hello", "Hello, {name}!")
        assert pm.get("hello") == "Hello, {name}!"

    def test_register_multiple_versions(self):
        pm = PromptManager()
        pm.register("hello", "Hello, {name}!", version="v1")
        pm.register("hello", "Hi, {{ name }}!", version="v2")
        assert pm.get("hello", "v1") == "Hello, {name}!"
        assert pm.get("hello", "v2") == "Hi, {{ name }}!"

    def test_get_missing_prompt_raises(self):
        pm = PromptManager()
        with pytest.raises(PromptNotFoundError):
            pm.get("missing")

    def test_get_missing_version_raises(self):
        pm = PromptManager()
        pm.register("hello", "Hello")
        with pytest.raises(PromptNotFoundError):
            pm.get("hello", "v99")

    def test_list_versions(self):
        pm = PromptManager()
        pm.register("greet", "A", version="v1")
        pm.register("greet", "B", version="v2")
        assert pm.list_versions("greet") == ["v1", "v2"]

    def test_list_prompts(self):
        pm = PromptManager()
        pm.register("a", "A")
        pm.register("b", "B")
        assert pm.list_prompts() == ["a", "b"]

    # ------------------------------------------------------------------ #
    # 文件加载
    # ------------------------------------------------------------------ #
    def test_load_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("Prompt from file: {var}")
            path = f.name

        pm = PromptManager()
        pm.load_from_file(path, name="file_prompt")
        assert pm.get("file_prompt") == "Prompt from file: {var}"

        Path(path).unlink()

    def test_load_from_directory_flat(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.txt").write_text("flat prompt", encoding="utf-8")
            pm = PromptManager()
            count = pm.load_from_directory(tmpdir)
            assert count == 1
            assert pm.get("test") == "flat prompt"

    def test_load_from_directory_versioned_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "story_v1.txt").write_text("v1 content", encoding="utf-8")
            (Path(tmpdir) / "story_v2.txt").write_text("v2 content", encoding="utf-8")
            pm = PromptManager()
            pm.load_from_directory(tmpdir)
            assert pm.get("story", "v1") == "v1 content"
            assert pm.get("story", "v2") == "v2 content"

    def test_load_from_directory_nested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "prompts" / "standup").mkdir(parents=True)
            (root / "prompts" / "standup" / "default.txt").write_text("standup default", encoding="utf-8")
            (root / "prompts" / "standup" / "v2.txt").write_text("standup v2", encoding="utf-8")
            pm = PromptManager()
            pm.load_from_directory(root / "prompts")
            assert pm.get("standup", "default") == "standup default"
            assert pm.get("standup", "v2") == "standup v2"

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #
    def test_render_str_format(self):
        pm = PromptManager()
        pm.register("greet", "Hello, {name}!")
        result = pm.render("greet", {"name": "World"})
        assert result == "Hello, World!"

    def test_render_jinja2(self):
        pm = PromptManager()
        pm.register("jinja", "Hello, {{ name }}! {% if upper %}WELCOME{% endif %}")
        result = pm.render("jinja", {"name": "World", "upper": True})
        assert "Hello, World!" in result
        assert "WELCOME" in result

    def test_render_missing_variable_fallback(self):
        pm = PromptManager()
        pm.register("greet", "Hello, {name}!")
        result = pm.render("greet", {})
        # str.format 遇到缺失变量会保留原始模板（因为我们 catch 了 KeyError）
        assert "{name}" in result

    # ------------------------------------------------------------------ #
    # A/B 测试
    # ------------------------------------------------------------------ #
    def test_ab_version_even(self):
        pm = PromptManager()
        pm.register("ab", "A", version="v1")
        pm.register("ab", "B", version="v2")
        version = pm.get_ab_version("ab", seed=42)
        assert version in ("v1", "v2")

    def test_ab_version_weighted(self):
        pm = PromptManager()
        pm.register("ab", "A", version="v1")
        pm.register("ab", "B", version="v2")
        # 固定种子使结果可复现
        version = pm.get_ab_version("ab", config={"v1": 1.0, "v2": 0.0}, seed=1)
        assert version == "v1"

    def test_render_ab(self):
        pm = PromptManager()
        pm.register("ab", "Version A", version="v1")
        pm.register("ab", "Version B", version="v2")
        version, text = pm.render_ab("ab", config={"v1": 1.0, "v2": 0.0}, seed=1)
        assert version == "v1"
        assert text == "Version A"

    def test_ab_version_missing_prompt_raises(self):
        pm = PromptManager()
        with pytest.raises(PromptNotFoundError):
            pm.get_ab_version("missing")
