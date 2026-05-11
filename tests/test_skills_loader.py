"""Skill 插件加载器测试。"""

import tempfile
from pathlib import Path

import pytest

from comedy_agent.skills.loader import (
    SkillMeta,
    _build_args_schema,
    _create_declarative_skill,
    load_plugin_skills,
)


class TestSkillMeta:
    """测试 SKILL.md 解析。"""

    def test_parse_basic(self):
        md = (
            "# Test Skill\n\n"
            "## 描述\n\n"
            "这是一个测试 Skill。\n\n"
            "## 参数\n\n"
            "| 名称 | 类型 | 必填 | 描述 |\n"
            "|------|------|------|------|\n"
            "| topic | string | 是 | 主题 |\n"
            "| count | int | 否 | 数量 |\n"
        )
        meta = SkillMeta.from_markdown(md, Path("/tmp/test"))
        assert meta.name == "Test Skill"
        assert "测试 Skill" in meta.description
        assert len(meta.parameters) == 2
        assert meta.parameters[0]["name"] == "topic"
        assert meta.parameters[0]["type"] == "string"
        assert meta.parameters[0]["required"] is True

    def test_parse_with_defaults(self):
        md = (
            "# Demo Skill\n\n"
            "## 描述\n\n"
            "演示用。\n\n"
            "## 参数\n\n"
            "| 名称 | 类型 | 必填 | 描述 | 默认值 |\n"
            "|------|------|------|------|--------|\n"
            "| style | string | 否 | 风格 | 日常观察 |\n"
            "| duration | int | 否 | 时长 | 3 |\n"
        )
        meta = SkillMeta.from_markdown(md, Path("/tmp/demo"))
        assert meta.parameters[0].get("default") == "日常观察"
        assert meta.parameters[1].get("default") == "3"

    def test_parse_task_type(self):
        md = (
            "# Analyze Skill\n\n"
            "## 描述\n\n"
            "分析用。\n\n"
            "## 任务类型\n\n"
            "analytical\n\n"
            "## 参数\n\n"
            "| 名称 | 类型 | 必填 | 描述 |\n"
            "|------|------|------|------|\n"
            "| query | string | 是 | 查询 |\n"
        )
        meta = SkillMeta.from_markdown(md, Path("/tmp/analyze"))
        assert meta.task_type == "analytical"

    def test_parse_default_task_type(self):
        md = (
            "# Simple Skill\n\n"
            "## 描述\n\n"
            "简单 Skill。\n"
        )
        meta = SkillMeta.from_markdown(md, Path("/tmp/simple"))
        assert meta.task_type == "creative"


class TestBuildArgsSchema:
    """测试动态 Args Schema 构建。"""

    def test_required_and_optional(self):
        params = [
            {"name": "topic", "type": "string", "required": True, "description": "主题", "default": None},
            {"name": "style", "type": "string", "required": False, "description": "风格", "default": "日常"},
        ]
        schema = _build_args_schema(params)
        assert "topic" in schema.model_fields
        assert "style" in schema.model_fields
        # 验证默认值
        instance = schema(topic="测试", style="幽默")
        assert instance.style == "幽默"
        assert instance.topic == "测试"

    def test_type_conversion(self):
        params = [
            {"name": "count", "type": "int", "required": False, "description": "", "default": "5"},
            {"name": "ratio", "type": "float", "required": False, "description": "", "default": "0.5"},
        ]
        schema = _build_args_schema(params)
        instance = schema()
        assert instance.count == 5
        assert instance.ratio == 0.5


class TestDeclarativeSkill:
    """测试声明式 Skill 生成。"""

    def test_skill_metadata(self):
        meta = SkillMeta(
            name="test_decl",
            description="A test skill.",
            parameters=[
                {"name": "topic", "type": "string", "required": True, "description": "主题", "default": None},
            ],
            skill_dir=Path("/tmp/test"),
        )
        meta.prompt_template = "Tell me about {topic}"
        cls = _create_declarative_skill(meta)
        assert cls.model_fields["name"].default == "test_decl"
        assert cls.model_fields["description"].default == "A test skill."
        assert cls.model_fields["args_schema"].default is not None


class TestLoadPluginSkills:
    """测试插件目录扫描与加载。"""

    def test_loads_declarative_skill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "my_skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "# My Skill\n\n## 描述\n\nMy desc.\n\n## 参数\n\n"
                "| 名称 | 类型 | 必填 | 描述 |\n"
                "|------|------|------|------|\n"
                "| query | string | 是 | 查询 |\n",
                encoding="utf-8",
            )
            (skill_dir / "prompt.txt").write_text(
                "Answer: {query}", encoding="utf-8"
            )

            skills = load_plugin_skills(tmpdir)
            assert len(skills) == 1
            assert skills[0].name == "My Skill"

    def test_skips_missing_skill_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "empty"
            skill_dir.mkdir()
            (skill_dir / "prompt.txt").write_text("Hi")

            skills = load_plugin_skills(tmpdir)
            assert len(skills) == 0

    def test_skips_hidden_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / ".git").mkdir()
            (Path(tmpdir) / "__pycache__").mkdir()

            skills = load_plugin_skills(tmpdir)
            assert len(skills) == 0

    def test_loads_multiple_skills(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                d = Path(tmpdir) / f"skill_{i}"
                d.mkdir()
                (d / "SKILL.md").write_text(
                    f"# Skill {i}\n\n## 描述\n\nDesc {i}.\n",
                    encoding="utf-8",
                )
                (d / "prompt.txt").write_text(f"Prompt {i}", encoding="utf-8")

            skills = load_plugin_skills(tmpdir)
            assert len(skills) == 3
            names = {s.name for s in skills}
            assert names == {"Skill 0", "Skill 1", "Skill 2"}
