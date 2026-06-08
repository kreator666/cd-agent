"""情绪 Skill —— 注入情绪节奏及对话语气词。

为场景描述或对白注入特定的情绪节奏（热血、悬疑、治愈、压抑等）。
"""

from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class EmotionArgs(BaseModel):
    """情绪参数 Schema。"""

    text: str = Field(description="需要注入情绪的文本")
    emotion: str = Field(description="情绪类型：热血 / 悬疑 / 治愈 / 压抑 / 高燃 / 催泪")


class EmotionSkill(ComedySkill):
    """情绪注入器。

    为文本注入特定的情绪节奏和对话语气词。
    """

    task_type: str = "creative"
    name: str = "emotion"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "情绪注入。输入文本和情绪类型，输出带有该情绪节奏和语气词的版本。"
    )
    args_schema: type[BaseModel] = EmotionArgs

    SYSTEM_PROMPT: str = (
        "你是一位情绪节奏助手。请根据指定的情绪类型，"
        "为文本注入相应的情绪节奏、语气词和氛围描写。"
        "可以添加动作提示（如'握拳'、'深呼吸'）来强化情绪表达。"
        "不改变原文的核心情节，只调整情绪张力和节奏。"
    )

    def _run(
        self,
        text: str,
        emotion: str,
        user_id: str | None = None,
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", f"情绪类型：{emotion}\n\n原文：\n{text}\n\n请注入该情绪节奏，只输出改写后的文本。"),
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
        emotion: str,
        user_id: str | None = None,
    ) -> str:
        return self._run(text, emotion, user_id=user_id)
