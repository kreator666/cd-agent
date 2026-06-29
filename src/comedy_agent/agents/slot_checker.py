"""槽位检查 Worker。

检查 4 个维度槽位是否已填满：
- 已填满或信息已足够：进入 analyzing，由 Context Analyzer 基于完整历史生成 analysis。
- 未填满且信息不足：返回引导消息，要求用户继续通过 @ 选择填充或继续聊天。
"""

from __future__ import annotations

import logging
from typing import Any

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

_REQUIRED_SLOTS = ("话题", "态度", "偏见", "情绪")

# 明确触发大纲/创作的口令
_START_CREATION_KEYWORDS = ("开始创作", "出大纲", "定大纲", "写大纲", "开始写", "生成大纲")

# 自由对话轮数阈值：用户消息数 >= 该值时，认为信息足够，可进入分析
_MIN_USER_TURNS = 3


class SlotCheckingAgent:
    """槽位检查 Agent。"""

    def run(self, state: ComedyState, llm: Any | None = None) -> dict[str, Any]:
        """检查槽位完整性并决定下一步。

        Args:
            state: 当前图状态。
            llm: 预留参数，当前实现基于规则检查，暂不使用 LLM。

        Returns:
            若信息足够：``phase=analyzing``
            若信息不足：``phase=consulting``
        """
        slots = state.slots or {}
        missing = [s for s in _REQUIRED_SLOTS if not slots.get(s)]

        if self._should_analyze(state, missing):
            logger.debug("slot_checker: information sufficient, move to analyzing")
            return {"phase": "analyzing"}

        logger.debug("slot_checker: missing %s, route to guide", missing)
        # 不直接输出引导语，交给 GuideAgent 生成 A/B/C 选项
        return {"phase": "consulting"}

    def _should_analyze(self, state: ComedyState, missing: list[str]) -> bool:
        """判断是否可以进入分析阶段。"""
        # 4 个维度槽位已显式填满
        if not missing:
            return True

        # 用户明确触发创作/大纲
        user_input = (state.user_input or "").strip()
        if any(kw in user_input for kw in _START_CREATION_KEYWORDS):
            return True

        # 自由对话已积累足够轮数
        user_turns = sum(1 for m in (state.messages or []) if getattr(m, "type", None) == "human")
        if user_turns >= _MIN_USER_TURNS:
            return True

        return False
