"""Agent Orchestrator —— 接收用户输入并路由到对应 Skill。

预留接口，将在任务 1.3 中实现。
"""

from typing import Any


class AgentOrchestrator:
    """Agent 主控：最简 Orchestrator。"""

    def __init__(self) -> None:
        self.skills: list[Any] = []

    def register_skill(self, skill: Any) -> None:
        """注册 Skill。"""
        self.skills.append(skill)

    def run(self, user_input: str) -> str:
        """接收用户输入，路由到对应 Skill 执行。

        Args:
            user_input: 用户的自然语言输入。

        Returns:
            str: Agent 的输出结果。
        """
        raise NotImplementedError("将在任务 1.3 中实现。")
