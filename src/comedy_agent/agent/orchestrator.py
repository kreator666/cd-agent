"""Agent Orchestrator —— 接收用户输入并路由到对应 Skill。

基于 LangChain 的 ``create_agent``（LangGraph）实现最简 Agent 主控。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from comedy_agent.core.observability import get_metrics, get_tracer
from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.models.factory import ModelFactory
from comedy_agent.skills.base import ComedySkill

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "你是一个喜剧创作助手，擅长根据用户需求调用合适的创作工具完成脱口秀、相声、"
    "小品等喜剧内容的创作与分析。"
)


class AgentOrchestrator:
    """Agent 主控：最简 Orchestrator。

    负责管理 Skill（Tool）集合，构建 LangChain Agent，
    并将用户输入路由到合适的 Skill 执行。
    """

    def __init__(
        self,
        model_name: str | None = None,
        system_prompt: str | None = None,
        memory: UnifiedMemory | None = None,
    ) -> None:
        """初始化 Orchestrator。

        Args:
            model_name: 模型标识，为 ``None`` 时使用 ``settings.default_model``。
            system_prompt: 系统提示词，覆盖默认值。
            memory: 可选的统一记忆接口，用于注入用户上下文。
        """
        self.model_name = model_name
        self.llm = ModelFactory.get_model(model_name)
        self.tools: list[BaseTool] = []
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.memory = memory
        self._agent: Any | None = None

    # ------------------------------------------------------------------ #
    # Skill 管理
    # ------------------------------------------------------------------ #
    def register_skill(self, skill: BaseTool) -> None:
        """注册 Skill（Tool）。

        注册新 Skill 后会重置内部 Agent 缓存，下次 ``run`` 时自动重建。
        如果 Orchestrator 指定了 model_name，会同步传播给 ComedySkill。
        """
        if isinstance(skill, ComedySkill) and self.model_name is not None:
            skill.model_name = self.model_name
        self.tools.append(skill)
        self._agent = None
        logger.info("Registered skill: %s", skill.name)

    def list_skills(self) -> list[str]:
        """返回已注册的所有 Skill 名称列表。"""
        return [tool.name for tool in self.tools]

    # ------------------------------------------------------------------ #
    # Agent 构建与执行
    # ------------------------------------------------------------------ #
    def _build_agent(self) -> Any:
        """构建或复用 LangChain Agent（CompiledStateGraph）。"""
        if self._agent is not None:
            return self._agent

        self._agent = create_agent(
            model=self.llm,
            tools=self.tools or None,
            system_prompt=self.system_prompt,
        )
        logger.debug(
            "Agent built with %d tool(s): %s",
            len(self.tools),
            self.list_skills(),
        )
        return self._agent

    def _build_memory_system_prompt(self, user_id: str | None = None) -> str | None:
        """若配置了 memory 和 user_id，构建包含用户记忆的 system prompt。"""
        if self.memory and user_id:
            memory_text = self.memory.build_context_text(user_id)
            if memory_text:
                return (
                    f"{self.system_prompt}\n\n"
                    f"【关于用户】\n"
                    f"以下是该用户的历史偏好与创作习惯，请在回答时参考：\n\n"
                    f"{memory_text}\n"
                    f"【关于用户结束】"
                )
        return None

    def run(
        self,
        user_input: str,
        chat_history: list[tuple[str, str]] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """接收用户输入，由 Agent 路由并执行对应 Skill。

        Args:
            user_input: 用户的自然语言输入。
            chat_history: 可选的历史消息列表，格式为 ``[(role, content), ...]``。
            user_id: 可选的用户标识，若配置了 memory 则会注入用户上下文。

        Returns:
            dict: 包含 ``output``（最终文本输出）和 ``messages``（完整消息链）的结果字典。
        """
        tracer = get_tracer()
        metrics = get_metrics()

        with tracer.span(
            "agent.run",
            input_data={"user_input": user_input[:200], "user_id": user_id},
            metadata={
                "model": self.model_name,
                "skills": self.list_skills(),
            },
        ) as span:
            agent = self._build_agent()

            messages: list[Any] = []

            # 若存在用户记忆，作为第一条 system message 注入
            memory_prompt = self._build_memory_system_prompt(user_id)
            if memory_prompt:
                messages.append(("system", memory_prompt))
            elif self.system_prompt:
                messages.append(("system", self.system_prompt))

            if chat_history:
                for role, content in chat_history:
                    messages.append((role, content))
            messages.append(("human", user_input))

            result = agent.invoke({"messages": messages})

            # 提取最后一条 AI 消息作为输出
            msg_list: list[BaseMessage] = result.get("messages", [])
            output = ""
            for msg in reversed(msg_list):
                if isinstance(msg, AIMessage):
                    output = str(msg.content)
                    break

            span.output_data = {"output": output[:200]}
            metrics.record("agent.run.duration_ms", span.duration_ms)
            metrics.record(
                "agent.run.tokens",
                len(str(msg_list)),
                tags={"model": self.model_name or "unknown"},
            )

            return {
                "output": output,
                "messages": msg_list,
            }

    async def arun(
        self,
        user_input: str,
        chat_history: list[tuple[str, str]] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """``run`` 的异步版本。"""
        tracer = get_tracer()
        metrics = get_metrics()

        with tracer.span(
            "agent.arun",
            input_data={"user_input": user_input[:200], "user_id": user_id},
            metadata={"model": self.model_name, "skills": self.list_skills()},
        ) as span:
            agent = self._build_agent()

            messages: list[Any] = []

            memory_prompt = self._build_memory_system_prompt(user_id)
            if memory_prompt:
                messages.append(("system", memory_prompt))
            elif self.system_prompt:
                messages.append(("system", self.system_prompt))

            if chat_history:
                for role, content in chat_history:
                    messages.append((role, content))
            messages.append(("human", user_input))

            result = await agent.ainvoke({"messages": messages})

            msg_list: list[BaseMessage] = result.get("messages", [])
            output = ""
            for msg in reversed(msg_list):
                if isinstance(msg, AIMessage):
                    output = str(msg.content)
                    break

            span.output_data = {"output": output[:200]}
            metrics.record("agent.arun.duration_ms", span.duration_ms)

            return {
                "output": output,
                "messages": msg_list,
            }
