"""加点盐 Skill —— 给日常文本加一点幽默。

不改变原意，根据盐度级别调整幽默程度。
"""

import sys
from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


# 从 loader 注入的 meta 读取提示词（如果存在）
_meta = getattr(sys.modules[__name__], "_skill_meta", None)


class AddSaltArgs(BaseModel):
    """加点盐参数 Schema（PRD v2 扩展支持 IP 风格注入）。"""

    text: str = Field(description="需要润色的原始文本")
    salt_level: str = Field(
        default="medium",
        description="盐度级别：light（约10%）/ medium（约20%）/ heavy（约30%）",
    )
    intensity: str = Field(
        default="medium",
        description="加梗强度（与 salt_level 同义，优先使用）：light / medium / heavy",
    )
    ip_role_prompt: str | None = Field(
        default=None, description="可选的 IP 角色风格提示片段"
    )


class AddSaltSkill(ComedySkill):
    """幽默润色器。

    为日常文本注入适度幽默感，保持原意不变。
    """

    task_type: str = "fast"
    name: str = "add_salt"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "给日常文本加一点幽默。输入原文和盐度级别，"
        "输出润色后的幽默版本，不改变原意。"
    )
    args_schema: type[BaseModel] = AddSaltArgs

    SYSTEM_PROMPT: str = (
        _meta.system_prompt
        if _meta and _meta.system_prompt
        else (
            "你是一位幽默润色助手。请严格遵循以下规则：\n"
            "1. 不改变原文的核心意思和关键信息。\n"
            "2. 根据要求的盐度级别，为文本注入适度幽默感。\n"
            "3. 只输出润色后的最终文本，不要添加解释、分析或格式标签。\n"
            "4. 保持原文的语言风格和场景。"
        )
    )

    def _build_system_prompt(self, ip_role_prompt: str | None = None) -> str:
        base = self.SYSTEM_PROMPT
        if ip_role_prompt:
            base += (
                f"\n\n【风格要求】\n"
                f"请模仿以下 IP 角色的语气进行改写：\n"
                f"{ip_role_prompt}\n"
                f"在改写时，必须保留原意，同时融入该角色的典型表达习惯和语气特征。"
            )
        return base

    def _build_user_prompt(self, text: str, intensity: str) -> str:
        level_desc = {
            "light": "约10%（轻微调味，点到为止）",
            "medium": "约20%（适度幽默，自然流露）",
            "heavy": "约30%（重度调味，明显搞笑）",
        }.get(intensity, "约20%（适度幽默，自然流露）")
        return (
            f"请对以下文本进行幽默润色，不改变原意，幽默程度{level_desc}：\n\n{text}"
        )

    def _run(
        self,
        text: str,
        salt_level: str = "medium",
        intensity: str | None = None,
        ip_role_prompt: str | None = None,
        user_id: str | None = None,
    ) -> str:
        # 向后兼容：salt_level 映射为 intensity
        effective_intensity = intensity or salt_level
        system = self._build_system_prompt(ip_role_prompt)
        prompt = ChatPromptTemplate.from_messages([
            ("system", system),
            ("human", self._build_user_prompt(text, effective_intensity)),
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
        salt_level: str = "medium",
        intensity: str | None = None,
        ip_role_prompt: str | None = None,
        user_id: str | None = None,
    ) -> str:
        return self._run(text, salt_level, intensity=intensity, ip_role_prompt=ip_role_prompt, user_id=user_id)
