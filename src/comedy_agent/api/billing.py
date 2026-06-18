"""模型调用计费工具函数。

与 ModelFactory 的 UsageCallbackHandler 配合：
- 调用模型前执行 ``reset_model_usage()``
- 调用模型后执行 ``charge_model_usage(...)`` 扣费并记录消费明细
"""

from __future__ import annotations

import logging
from typing import Any

from comedy_agent.api.state import state
from comedy_agent.memory.models import TokenConsumptionData
from comedy_agent.models.usage_tracker import (
    ModelUsage,
    get_model_usage,
    reset_model_usage,
)

logger = logging.getLogger(__name__)


def start_usage_tracking() -> None:
    """开始一次新的用量追踪。"""
    reset_model_usage()


def charge_model_usage(
    user_id: str,
    endpoint: str,
    description: str | None = None,
    session_id: str | None = None,
    fallback_cost: int = 0,
) -> dict[str, Any]:
    """根据本次追踪到的模型用量扣费并写入消费记录。

    Args:
        user_id: 用户 ID。
        endpoint: 调用入口，如 ``/chat``、``/salt``。
        description: 消费描述。
        session_id: 关联会话 ID（可选）。
        fallback_cost: 当模型未返回 usage 时的兜底扣费数量。

    Returns:
        dict: 包含 ``cost``、``usage``、``record_id`` 的字典。
    """
    if state.memory is None:
        return {"cost": 0, "usage": None, "record_id": None}

    usage = get_model_usage()
    cost = usage.total_tokens if usage else fallback_cost

    # 兜底：如果连 fallback_cost 也没有，至少按 0 处理，避免异常
    if cost <= 0:
        cost = fallback_cost

    if cost > 0:
        ok = state.memory.deduct_tokens(user_id, cost)
        if not ok:
            logger.warning("Token deduction failed for user %s, cost %d", user_id, cost)

    record = TokenConsumptionData(
        user_id=user_id,
        session_id=session_id,
        endpoint=endpoint,
        model=usage.model if usage else None,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        total_tokens=usage.total_tokens if usage else 0,
        cost=cost,
        description=description,
    )
    saved = state.memory.save_consumption_record(record)

    return {
        "cost": cost,
        "usage": usage,
        "record_id": saved.consumption_id,
    }


def get_usage_summary() -> ModelUsage | None:
    """获取当前累计用量（不扣费）。"""
    return get_model_usage()
