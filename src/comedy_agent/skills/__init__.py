"""Skill 体系：喜剧创作技能与辅助工具。"""

from comedy_agent.skills.base import ComedySkill
from comedy_agent.skills.standup import StandupSkill
from comedy_agent.skills.crosstalk import CrosstalkSkill
from comedy_agent.skills.sketch import SketchSkill
from comedy_agent.skills.sitcom import SitcomSkill
from comedy_agent.skills.manzai import ManzaiSkill
from comedy_agent.skills.japanese_sketch import JapaneseSketchSkill
from comedy_agent.skills.add_salt import AddSaltSkill
from comedy_agent.skills.topic import TopicSkill
from comedy_agent.skills.attitude import AttitudeSkill
from comedy_agent.skills.emotion import EmotionSkill
from comedy_agent.skills.genre import GenreSkill
from comedy_agent.skills.rule_persona import RulePersonaSkill
from comedy_agent.skills.script_composer import ScriptComposerSkill

__all__ = [
    "ComedySkill",
    "StandupSkill",
    "CrosstalkSkill",
    "SketchSkill",
    "SitcomSkill",
    "ManzaiSkill",
    "JapaneseSketchSkill",
    "AddSaltSkill",
    "TopicSkill",
    "AttitudeSkill",
    "EmotionSkill",
    "GenreSkill",
    "RulePersonaSkill",
    "ScriptComposerSkill",
]
