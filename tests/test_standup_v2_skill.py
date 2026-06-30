"""standup_v2 Skill 加载与教练模式测试。"""

from __future__ import annotations

from pathlib import Path

from comedy_agent.core.skill_loader import load_skill_config


def test_standup_v2_loads_as_coach_skill():
    cfg = load_skill_config(Path("skills/standup_v2"))
    assert cfg is not None
    assert cfg.id == "standup_v2"
    assert cfg.metadata.get("mode") == "coach"
    assert cfg.metadata.get("kind") == "standup"


def test_standup_v2_system_prompt_fused():
    cfg = load_skill_config(Path("skills/standup_v2"))
    prompt = cfg.system_prompt
    assert "BVT" in prompt
    assert "ER 法" in prompt or "ER法" in prompt
    assert "五感幽默" in prompt
    assert "教练" in prompt
    assert "四维输入" in prompt
    assert "难 / 怪 / 怕 / 蠢" in prompt or "难/怪/怕/蠢" in prompt


def test_standup_v2_prompt_template_is_coach_template():
    cfg = load_skill_config(Path("skills/standup_v2"))
    template = cfg.prompt_template
    assert "教练任务" in template
    assert "不要直接写出段落正文" in template
    assert "{{ user_input }}" in template
    assert "{{ section_goal }}" in template
    assert "{{ slots }}" in template
