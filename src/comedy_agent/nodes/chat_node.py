"""Phase 0 单 Agent Chat 节点。

复用 v3 的 ModelFactory，将用户输入交给 LLM 生成回复。
优先使用 `state.messages`（LangGraph checkpoint 消息链），为空时回退到 `state.chat_history`。
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
    """Chat 节点：根据当前状态调用 LLM 生成回复。

    Args:
        state: 当前图状态。

    Returns:
        dict: 包含 ``output``、``messages``、``phase`` 的更新字典。
    """
    model_name = state.model or settings.default_model
    llm = ModelFactory.get_model(model_name)

    # 优先使用 state.messages（LangGraph checkpoint 维护的完整消息链）
    appended_user_message: HumanMessage | None = None
    if state.messages:
        messages = list(state.messages)
        _ensure_system_prompt(messages)
        appended_user_message = _ensure_user_input(messages, state.user_input)
        # checkpoint 已包含历史，返回新增的用户输入（如有）和 AI 回复，避免 add_messages 重复
        return_full_messages = False
    else:
        # 回退到 chat_history（旧入口 /chat、/salt、/speed 等使用）
        messages = [SystemMessage(content=DEFAULT_SYSTEM_PROMPT)]
        if state.chat_history:
            for role, content in state.chat_history:
                if role == "system":
                    messages.append(SystemMessage(content=content))
                elif role == "ai":
                    messages.append(AIMessage(content=content))
                else:
                    messages.append(HumanMessage(content=content))
        if state.user_input:
            messages.append(HumanMessage(content=state.user_input))
        # 没有 checkpoint 历史，需要把完整消息链返回给 LangGraph
        return_full_messages = True

    logger.debug("chat_node invoke with %d messages, model=%s", len(messages), model_name)

    response = llm.invoke(messages)
    output = str(response.content)

    if return_full_messages:
        output_messages = messages + [AIMessage(content=output)]
    else:
        output_messages = []
        if appended_user_message is not None:
            output_messages.append(appended_user_message)
        output_messages.append(AIMessage(content=output))

    return {
        "output": output,
        "messages": output_messages,
        "phase": "complete",
        "response_type": "guide",
    }


def _ensure_system_prompt(messages: list) -> None:
    """若消息链中无 SystemMessage，在头部追加默认系统提示。"""
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages.insert(0, SystemMessage(content=DEFAULT_SYSTEM_PROMPT))


def _ensure_user_input(messages: list, user_input: str) -> HumanMessage | None:
    """若消息链末尾不是当前用户输入，则追加并返回追加的消息。"""
    if not user_input:
        return None
    if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == user_input:
        return None
    msg = HumanMessage(content=user_input)
    messages.append(msg)
    return msg
