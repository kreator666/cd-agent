"""Skill 基类 —— 所有喜剧 Skill 的抽象接口。

预留接口，将在任务 1.4 / 2.1 / 2.2 中完善。
"""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.tools import BaseTool


class ComedySkill(BaseTool, ABC):
    """喜剧 Skill 抽象基类。

    每个 Skill 对应一种喜剧创作能力（脱口秀、相声、小品等），
    或辅助能力（笑点分析、剧本评估等）。
    """

    @abstractmethod
    def _run(self, *args: Any, **kwargs: Any) -> str:
        """同步执行 Skill。"""
        ...

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """异步执行 Skill（默认调用同步版本）。"""
        return self._run(*args, **kwargs)
