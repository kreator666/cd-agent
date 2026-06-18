"""风格模仿 Skill —— IP 角色语气模仿。

根据角色风格提示片段，对输入文本进行风格化改写。
可被极速版和专业版共用。
"""

from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class StyleMimicArgs(BaseModel):
    """风格模仿参数 Schema。"""

    text: str = Field(description="需要改写的原始文本")
    style_prompt: str = Field(description="IP 角色风格提示片段")


class StyleMimicSkill(ComedySkill):
    """IP 角色风格模仿器。

    将输入文本改写为指定 IP 角色的语气风格。
    """

    task_type: str = "creative"
    name: str = "style_mimic"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "IP 角色风格模仿。输入原文和角色风格提示，"
        "输出带有该角色语气的改写文本。"
    )
    args_schema: type[BaseModel] = StyleMimicArgs

    SYSTEM_PROMPT: str = (
        "你是一位专业的风格模仿助手。请严格遵循以下规则：\n"
        "1. 不改变原文的核心意思和关键信息。\n"
        "2. 根据给定的角色风格提示，调整语气、措辞和表达方式。\n"
        "3. 只输出改写后的最终文本，不要添加解释、分析或格式标签。"
    )

    def _run(
        self,
        text: str,
        style_prompt: str,
        user_id: str | None = None,
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", f"【角色风格】\n{style_prompt}\n\n【原文】\n{text}\n\n请按上述角色风格改写原文，只输出改写后的文本。"),
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
        style_prompt: str,
        user_id: str | None = None,
    ) -> str:
        return self._run(text, style_prompt, user_id=user_id)
