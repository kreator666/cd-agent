"""写作节点：根据大纲逐段撰写内容。

Phase 2 委托给 WriterAgent。
"""

from __future__ import annotations

from comedy_agent.agents.writer import WriterAgent
from comedy_agent.core.config import settings
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

_agent = WriterAgent()


def write_node(state: ComedyState) -> dict:
    """写作节点。

    Args:
        state: 当前图状态。

    Returns:
        包含 ``sections`` 更新和 ``phase`` 的更新字典。
    """
    model_name = state.model or settings.creative_model
    llm = ModelFactory.get_model(model_name, task_type="creative")
    result = _agent.run(state, llm=llm)
    # 记录实际使用的模型，供后续润色/建议等节点保持模型一致
    result["model_used"] = model_name
    return result
