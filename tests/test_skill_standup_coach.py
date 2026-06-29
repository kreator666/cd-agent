"""standup_coach Skill 加载与内容测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from comedy_agent.core.skill_loader import load_skill_config


@pytest.fixture
def skill_dir():
    return Path("skills/standup_coach")


def test_standup_coach_skill_loads(skill_dir):
    cfg = load_skill_config(skill_dir)
    assert cfg is not None
    assert cfg.id == "standup_coach"
    assert cfg.name == "脱口秀教练"
    assert cfg.task_type == "creative"
    assert cfg.metadata.get("kind") == "standup"


def test_system_prompt_contains_key_frameworks(skill_dir):
    cfg = load_skill_config(skill_dir)
    prompt = cfg.system_prompt
    assert "BVT" in prompt
    assert "ER 法" in prompt or "ER法" in prompt
    assert "Setup-Punchline" in prompt or "Setup" in prompt
    assert "callback" in prompt.lower()
    assert "逐字稿" in prompt
    assert "四阶段输入" in prompt
    assert "难 / 怪 / 怕 / 蠢" in prompt or "难/怪/怕/蠢" in prompt


def test_prompt_template_contains_jinja_variables(skill_dir):
    cfg = load_skill_config(skill_dir)
    template = cfg.prompt_template
    assert "{{ user_input }}" in template
    assert "{{ outline }}" in template
    assert "{{ section_goal }}" in template
    assert "{{ slots }}" in template


def test_collection_prompt_exists_and_covers_four_dimensions(skill_dir):
    path = skill_dir / "collection_prompt.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "话题" in text
    assert "态度" in text
    assert "偏见" in text
    assert "情绪" in text
    assert "A." in text
    assert "B." in text
    assert "C." in text
    assert "回复:" in text
    assert "选项:" in text
