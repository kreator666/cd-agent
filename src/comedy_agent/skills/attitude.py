"""态度 Skill —— 附加态度倾向的措辞改写。

为文本注入特定的态度倾向（讽刺、崇拜、质疑、中立等）。
"""

from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class AttitudeArgs(BaseModel):
    """态度参数 Schema。"""

    text: str = Field(description="需要改写的文本")
    attitude: str = Field(description="态度类型：讽刺 / 崇拜 / 质疑 / 中立 / 鼓励 / 调侃")


class AttitudeSkill(ComedySkill):
    """态度改写器。

    为输入文本附加特定的态度倾向措辞。
    """

    task_type: str = "creative"
    name: str = "attitude"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "态度改写。输入文本和态度类型，输出带有该态度倾向的改写版本。"
    )
    args_schema: type[BaseModel] = AttitudeArgs

    SYSTEM_PROMPT: str = (
        "你是一位态度调整助手。请根据指定的态度类型，"
        "为文本改写措辞，使其体现出对应的态度倾向。"
        "不改变原文的核心信息，只调整语气和表达方式。"
    )

    def _run(
        self,
        text: str,
        attitude: str,
        user_id: str | None = None,
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", f"态度类型：{attitude}\n\n原文：\n{text}\n\n请按指定态度改写，只输出改写后的文本。"),
        ])
        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        if hasattr(result, "content"):
            return str(result.content)
        return str(result)

    async def _arun(
        self,
        text: str,
        attitude: str,
        user_id: str | None = None,
    ) -> str:
        return self._run(text, attitude, user_id=user_id)
