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

    # 任务类型，用于模型分层配置
    # creative: 创意任务（创作类）
    # analytical: 分析任务（评估/分析类）
    # fast: 快速响应任务
    task_type: str = "creative"

    # 用户指定的覆盖模型，优先级高于 task_type 分层配置
    model_name: str | None = None

    @abstractmethod
    def _run(self, *args: Any, **kwargs: Any) -> str:
        """同步执行 Skill。"""
        ...

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """异步执行 Skill（默认调用同步版本）。"""
        return self._run(*args, **kwargs)
