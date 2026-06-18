"""风格 Skill —— 全局风格迁移。

将文本改写为特定的全局风格（王家卫文艺风、古风、赛博朋克等）。
"""

from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class GenreArgs(BaseModel):
    """风格参数 Schema。"""

    text: str = Field(description="需要迁移风格的原始文本")
    genre: str = Field(description="目标风格：王家卫文艺风 / 古风 / 赛博朋克 / 纪实 / 黑色幽默 / 日式冷幽默")


class GenreSkill(ComedySkill):
    """全局风格迁移器。

    将输入文本改写为指定的全局风格。
    """

    task_type: str = "creative"
    name: str = "genre"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "全局风格迁移。输入原文和目标风格，输出该风格下的改写版本。"
    )
    args_schema: type[BaseModel] = GenreArgs

    SYSTEM_PROMPT: str = (
        "你是一位风格迁移助手。请根据指定的目标风格，"
        "对原文进行全局风格改写，包括句式、词汇、氛围和叙事节奏。"
        "不改变原文的核心情节和信息，只调整整体风格表达。"
    )

    def _run(
        self,
        text: str,
        genre: str,
        user_id: str | None = None,
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", f"目标风格：{genre}\n\n原文：\n{text}\n\n请按目标风格改写，只输出改写后的文本。"),
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
        genre: str,
        user_id: str | None = None,
    ) -> str:
        return self._run(text, genre, user_id=user_id)
