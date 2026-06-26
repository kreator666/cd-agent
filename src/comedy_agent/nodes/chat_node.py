"""Phase 0 单 Agent Chat 节点。

复用 v3 的 ModelFactory，将用户输入交给 LLM 生成回复。
后续 Phase 会被 Supervisor + Worker 架构取代，但本节点作为最小可运行骨架保留。
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from comedy_agent.core.config import settings
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "你是一个喜剧创作助手，擅长根据用户需求调用合适的创作工具完成脱口秀、相声、"
    "小品等喜剧内容的创作与分析。"
)


def chat_node(state: ComedyState) -> dict:
    """最简单的 Chat 节点：接收用户输入，调用 LLM，返回响应。

    Args:
        state: 当前图状态。

    Returns:
        dict: 包含 ``output``、``messages``、``phase`` 的更新字典。
    """
    # 选择模型：优先使用 state 中指定的模型，否则使用默认模型
    model_name = state.model or settings.default_model
    llm = ModelFactory.get_model(model_name)

    # 构建消息列表
    messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=DEFAULT_SYSTEM_PROMPT)
    ]

    # 追加历史消息
    if state.chat_history:
        for role, content in state.chat_history:
            if role == "system":
                messages.append(SystemMessage(content=content))
            elif role == "ai":
                messages.append(AIMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))

    # 追加当前用户输入
    if state.user_input:
        messages.append(HumanMessage(content=state.user_input))

    logger.debug("chat_node invoke with %d messages, model=%s", len(messages), model_name)

    # 调用 LLM（同步版本，API 层通过 ainvoke 调用）
    response = llm.invoke(messages)
    output = str(response.content)

    # 将 AI 回复追加到消息链（使用新列表，避免修改传入 LLM 的列表）
    output_messages = messages + [AIMessage(content=output)]

    return {
        "output": output,
        "messages": output_messages,
        "phase": "complete",
        "response_type": "guide",
    }
