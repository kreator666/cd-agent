"""话题 Skill —— 扩写话题背景及冲突点。

根据核心关键词，扩写出话题背景、冲突点和场景设定。
"""

from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class TopicArgs(BaseModel):
    """话题参数 Schema。"""

    keywords: str = Field(description="核心关键词或一句话主题")


class TopicSkill(ComedySkill):
    """话题扩写器。

    输入核心关键词，输出话题背景、冲突点和场景设定。
    """

    task_type: str = "creative"
    name: str = "topic"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "话题扩写。输入核心关键词，输出话题背景、冲突点和场景设定。"
    )
    args_schema: type[BaseModel] = TopicArgs

    SYSTEM_PROMPT: str = (
        "你是一位专业的话题策划助手。请根据用户给出的核心关键词，"
        "扩写出完整的话题背景、核心冲突点和推荐场景设定。"
        "输出简洁有力，适合短视频剧本创作参考。"
    )

    def _run(
        self,
        keywords: str,
        user_id: str | None = None,
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", f"核心关键词：{keywords}\n\n请扩写话题背景、冲突点和场景设定。"),
        ])
        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        if hasattr(result, "content"):
            return str(result.content)
        return str(result)

    async def _arun(
        self,
        keywords: str,
        user_id: str | None = None,
    ) -> str:
        return self._run(keywords, user_id=user_id)
