"""槽位填充 Worker。

解析用户输入中的 @  mention / 显式槽位声明，
更新 ``state.slots``（话题 / 态度 / 偏见 / 情绪）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

# 槽位名映射：支持中文标签、@别名、常见变体
_SLOT_ALIASES: dict[str, str] = {
    "话题": "话题",
    "topic": "话题",
    "主题": "话题",
    "态度": "态度",
    "attitude": "态度",
    "立场": "态度",
    "偏见": "偏见",
    "bias": "偏见",
    "刻板印象": "偏见",
    "情绪": "情绪",
    "emotion": "情绪",
    "基调": "情绪",
}

_REQUIRED_SLOTS = ("话题", "态度", "偏见", "情绪")

# 匹配模式：@话题 内容 / 话题：内容 / 我的话题是 内容 / 话题=内容
_SLOT_PATTERNS = [
    # @话题 内容
    re.compile(r"@\s*(?P<key>[^\s：:是=]+)\s+(?P<value>[^@\n]+?)(?=\s+@|\s*$)", re.DOTALL),
    # 话题：内容 / 话题是内容 / 我的话题是内容
    re.compile(r"(?:我的)?(?P<key>话题|态度|偏见|情绪|主题|立场|基调)\s*[:：是=]\s*(?P<value>[^\n]+?)(?=\s+(?:我的)?(?:话题|态度|偏见|情绪|主题|立场|基调)\s*[:：是=]|$)", re.DOTALL),
]


class SlotFillingAgent:
    """槽位填充 Agent。"""

    def run(self, state: ComedyState, llm: Any | None = None) -> dict[str, Any]:
        """解析用户输入并更新槽位。

        Args:
            state: 当前图状态。
            llm: 预留参数，当前实现基于规则解析，暂不使用 LLM。

        Returns:
            包含 ``slots`` 与 ``phase=slot_checking`` 的更新字典。
        """
        slots = dict(state.slots or {})
        user_input = state.user_input or ""

        # 解析 @mention 与显式槽位声明
        extracted = self._extract_slots(user_input)
        for key, value in extracted.items():
            normalized = self._normalize_key(key)
            if normalized:
                slots[normalized] = value.strip()
                logger.debug("slot_filler: filled %s = %s", normalized, value.strip())

        return {
            "slots": slots,
            "phase": "slot_checking",
        }

    def _extract_slots(self, text: str) -> dict[str, str]:
        """从文本中提取槽位键值对。"""
        results: dict[str, str] = {}
        for pattern in _SLOT_PATTERNS:
            for match in pattern.finditer(text):
                key = match.group("key").strip()
                value = match.group("value").strip()
                if value:
                    results[key] = value
        return results

    def _normalize_key(self, key: str) -> str | None:
        """将别名归一化为标准槽位名。"""
        lowered = key.lower().strip().replace("专家", "").replace("达人", "")
        return _SLOT_ALIASES.get(lowered)

    @classmethod
    def missing_slots(cls, slots: dict[str, str] | None) -> list[str]:
        """返回尚未填充的必填槽位。"""
        slots = slots or {}
        return [s for s in _REQUIRED_SLOTS if not slots.get(s)]
