"""收尾节点：合并所有段落为完整输出。"""

from __future__ import annotations

import logging

from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)


def finalize_node(state: ComedyState) -> dict:
    """收尾节点。

    Args:
        state: 当前图状态。

    Returns:
        dict: 包含 output 和 phase = complete。
    """
    sections = state.sections
    if not sections:
        output = "（未生成内容）"
    else:
        output = "\n\n".join(
            f"第 {i+1} 段：\n{text}" for i, text in enumerate(sections)
        )

    logger.debug("finalize_node output length: %d", len(output))

    return {
        "output": output,
        "phase": "complete",
        "response_type": "script",
    }
