"""剧本编排 Skill —— 最终编排，输出结构化 Markdown 剧本。

将话题、态度、情绪、风格、人物画像等多个维度的输出整合为完整的结构化剧本。
"""

import sys
from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


_meta = getattr(sys.modules[__name__], "_skill_meta", None)


class ScriptComposerArgs(BaseModel):
    """剧本编排参数 Schema。"""

    outline: str = Field(description="创意大纲")
    context: str = Field(default="", description="前置 Skill 生成的上下文内容（话题/态度/情绪/风格/画像等）")


class ScriptComposerSkill(ComedySkill):
    """剧本编排器。

    整合多维度 Skill 输出，生成包含分镜、对白、场景说明的 Markdown 剧本。
    """

    task_type: str = "creative"
    name: str = "script_composer"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "剧本编排。输入创意大纲和前置 Skill 上下文，"
        "输出包含分镜、对白、场景说明的结构化 Markdown 剧本。"
    )
    args_schema: type[BaseModel] = ScriptComposerArgs

    SYSTEM_PROMPT: str = (
        _meta.system_prompt
        if _meta and _meta.system_prompt
        else (
            "你是一位专业的短视频剧本编排助手。\n"
            "请根据创意大纲和前置处理结果，编排成完整的结构化剧本。\n"
            "输出格式要求（Markdown）：\n"
            "1. 每集/每场以 ## 标题开头\n"
            "2. 场景说明以 **场景** 标注\n"
            "3. 对白格式：角色名：台词内容\n"
            "4. 动作提示以 （动作：...） 形式插入\n"
            "5. 拍摄建议以 > 引用块标注\n"
            "只输出最终剧本，不要添加总结或分析。"
        )
    )

    def _run(
        self,
        outline: str,
        context: str = "",
        user_id: str | None = None,
    ) -> str:
        user_msg = f"创意大纲：\n{outline}"
        if context:
            user_msg += f"\n\n【前置处理结果】\n{context}\n\n请整合以上内容，编排成完整的结构化 Markdown 剧本。"
        else:
            user_msg += "\n\n请编排成完整的结构化 Markdown 剧本。"
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", user_msg),
        ])
        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        if hasattr(result, "content"):
            return str(result.content)
        return str(result)

    async def _arun(
        self,
        outline: str,
        context: str = "",
        user_id: str | None = None,
    ) -> str:
        return self._run(outline, context=context, user_id=user_id)
