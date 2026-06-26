"""Skill 配置统一加载入口（供 Graph / Writer 使用）。

本模块是 ``comedy_agent.skills.loader`` 的薄封装，
面向 Writer Agent 和 state_modifier 提供只读的 SkillConfig，
避免它们直接依赖完整的 ComedySkill 工具链。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from comedy_agent.skills.loader import (
    SkillConfig,
    SkillExample,
    get_default_skill_config,
    load_skill_config,
    load_skill_configs,
)

__all__ = [
    "SkillConfig",
    "SkillExample",
    "load_skill_config",
    "load_skill_configs",
    "get_default_skill_config",
]
