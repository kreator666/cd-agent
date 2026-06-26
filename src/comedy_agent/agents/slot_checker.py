"""槽位检查 Worker。

检查 4 个维度槽位是否已填满：
- 未填满：返回引导消息，要求用户继续通过 @ 选择填充。
- 已填满：将槽位映射为 analysis，进入 planning。
"""

from __future__ import annotations

import logging
from typing import Any

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

_REQUIRED_SLOTS = ("话题", "态度", "偏见", "情绪")


class SlotCheckingAgent:
    """槽位检查 Agent。"""

    def run(self, state: ComedyState, llm: Any | None = None) -> dict[str, Any]:
        """检查槽位完整性并决定下一步。

        Args:
            state: 当前图状态。
            llm: 预留参数，当前实现基于规则检查，暂不使用 LLM。

        Returns:
            若槽位完整：``phase=planning`` + ``analysis``
            若槽位缺失：``phase=complete`` + ``response_type=guide`` + ``output`` 引导语
        """
        slots = state.slots or {}
        missing = [s for s in _REQUIRED_SLOTS if not slots.get(s)]

        if missing:
            logger.debug("slot_checker: missing %s, route to guide", missing)
            # 不直接输出引导语，交给 GuideAgent 生成 A/B/C 选项
            return {"phase": "consulting"}

        logger.debug("slot_checker: all slots filled, move to planning")
        return {
            "analysis": {
                "topic": slots["话题"],
                "attitude": slots["态度"],
                "bias": slots["偏见"],
                "emotion": slots["情绪"],
            },
            "phase": "planning",
        }
