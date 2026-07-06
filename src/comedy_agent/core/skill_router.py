"""Skill 路由器 —— 代码层条件路由，非模型判断。

根据用户输入中的 @ 提及、UI 显式选择、当前 State 中已有的 Skill 选择，
决定本次请求应使用的 `selected_skill` 与 `selected_style`。

当前仅保留 standup 写作 Skill。
"""

from __future__ import annotations

import logging
import re

from comedy_agent.core.config import settings
from comedy_agent.core.skill_loader import load_skill_configs
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

# 常见 Skill 名称/别名到 Skill ID 的映射
_SKILL_ALIASES: dict[str, str] = {
    "默认": "standup",
    "脱口秀": "standup",
}

# 哪些 metadata.kind 被视为写作类 Skill
_WRITING_KINDS = {"standup"}


def _list_writing_skill_ids() -> set[str]:
    """加载所有写作类 Skill 的 ID。当前仅保留 standup。"""
    configs = load_skill_configs(settings.skills_dir)
    return {
        cfg.id
        for cfg in configs
        if cfg.metadata.get("kind") in _WRITING_KINDS
        or cfg.id in _SKILL_ALIASES.values()
    }


def _extract_mention(user_input: str) -> str | None:
    """从用户输入中提取第一个 @ 提及的 Skill/风格标识。"""
    matches = re.findall(r"@([\u4e00-\u9fa5a-zA-Z0-9_\-]+)", user_input)
    if not matches:
        return None
    return matches[0].strip()


def resolve_skill(
    state: ComedyState,
    explicit_skill_id: str | None = None,
    explicit_style: str | None = None,
) -> dict[str, str | None]:
    """解析本次请求应使用的 Skill 与风格。

    优先级：
    1. 前端显式传入的 skill_id / style。
    2. 用户输入中的 @ 提及（如 @standup / @脱口秀）。
    3. State 中已保存的 selected_skill / selected_style（跨轮保留）。
    4. 兜底：standup。

    Args:
        state: 当前 LangGraph 状态。
        explicit_skill_id: UI 显式选择的 Skill ID。
        explicit_style: UI 显式选择的风格。

    Returns:
        {"selected_skill": str | None, "selected_style": str | None}
    """
    writing_ids = _list_writing_skill_ids()

    # 1. 显式选择
    skill_id = explicit_skill_id
    style = explicit_style

    # 2. @ 提及
    if not skill_id:
        mention = _extract_mention(state.user_input)
        if mention:
            # 先查别名，再查 ID，最后忽略非写作 Skill
            resolved = _SKILL_ALIASES.get(mention)
            if resolved and resolved in writing_ids:
                skill_id = resolved
            elif mention in writing_ids:
                skill_id = mention

    # 3. 保留已有选择
    if not skill_id:
        skill_id = state.selected_skill
    if not style:
        style = state.selected_style

    # 4. 兜底
    default_id = "standup"
    if not skill_id:
        skill_id = default_id

    # 如果解析出的 Skill 不是写作类，回退到默认写作 Skill
    if skill_id not in writing_ids:
        logger.warning("Skill %s 不是写作类 Skill，回退到 %s", skill_id, default_id)
        skill_id = default_id

    return {"selected_skill": skill_id, "selected_style": style}
