"""脱口秀创作 Skill —— 按模板规范输出。"""

import sys
from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


_meta = getattr(sys.modules[__name__], "_skill_meta", None)

# 终稿模式硬约束——覆盖模板中要求输出分析过程的指令
_OUTPUT_CONSTRAINT = (
    "【最终输出约束——覆盖上述所有格式要求】\n"
    "你只允许输出段子正文，适合演员直接上台表演的内容。\n"
    "严禁输出以下任何内容：主题、人设、核心观点、使用的喜剧机制、爆点分析。\n"
    "严禁输出分析过程、思考步骤、meta说明、创作思路。\n"
    "严禁使用 Markdown 标题（如 ##）来划分输出结构。\n"
    "输出必须是连续、干净的纯文本段落，不含任何结构标签。"
)

# Debug 模式说明
_DEBUG_NOTE = (
    "【Debug 模式】\n"
    "请输出完整的创作分析过程，包括：主题分析、人设设计、核心观点、\n"
    "使用的喜剧机制、爆点分析、创作思路。\n"
    "分析过程放在正文之前，用【分析过程】和【正文】两个标签分隔。"
)


class StandupArgs(BaseModel):
    """脱口秀创作参数 Schema。"""

    topic: str = Field(description="脱口秀主题")
    attitude: str = Field(description="创作者对话题的态度，如讽刺/自嘲/观察/批判/温情")
    bias: str = Field(description="可能存在的认知偏见或刻板印象，没有则写'无'")
    emotion: str = Field(description="目标情绪基调，如愤怒/荒诞/尴尬/温暖/无奈")
    duration: int = Field(default=3, description="预计时长（分钟），决定篇幅")


class StandupSkill(ComedySkill):
    """脱口秀段子生成器。"""

    task_type: str = "creative"
    name: str = "standup_generator"
    available_styles: ClassVar[list[str]] = ["日常观察", "自嘲", "社会讽刺", "职场", "黑色幽默", "吐槽", "意辰"]
    description: str = (
        "创作脱口秀段子。输入主题、风格、时长、受众，"
        "输出基于脱口秀输出模板 v2 的段子，包含预期违背、反逻辑、角色视角。"
    )
    args_schema: type[BaseModel] = StandupArgs

    SYSTEM_PROMPT: str = (
        _meta.system_prompt
        if _meta and _meta.system_prompt
        else "你是一位顶级中文单口喜剧编剧 + 开放麦演员 + 人类观察学家。"
    )

    def _build_user_prompt(
        self, topic: str, attitude: str, bias: str, emotion: str, duration: int
    ) -> str:
        template = (
            _meta.prompt_template
            if _meta and _meta.prompt_template
            else (
                "请创作一段关于「{topic}」的脱口秀段子。\n\n"
                "四维度创作要求：\n"
                "- 态度：{attitude}\n"
                "- 偏见注意：{bias}\n"
                "- 情绪基调：{emotion}\n"
                "- 时长：约{duration}分钟\n\n"
                "请严格围绕以上话题和四维度创作，不要偏离主题。"
            )
        )
        return template.format(
            topic=topic, attitude=attitude, bias=bias, emotion=emotion, duration=duration
        )

    def _run(
        self,
        topic: str,
        attitude: str,
        bias: str,
        emotion: str,
        duration: int = 3,
        user_id: str | None = None,
    ) -> str:
        docs = self._retrieve_knowledge(topic, user_id, kind="standup", style=style)
        knowledge_text = self._format_knowledge(docs)
        system_prompt = self.SYSTEM_PROMPT + "\n\n" + _OUTPUT_CONSTRAINT
        if knowledge_text:
            system_prompt += f"\n\n{knowledge_text}"
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", self._build_user_prompt(topic, attitude, bias, emotion, duration)),
        ])
        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        if hasattr(result, "content"):
            return str(result.content)
        return str(result)

    async def _arun(
        self,
        topic: str,
        style: str = "日常观察",
        duration: int = 3,
        audience: str = "通用",
        density: str = "标准",
        perspective_count: int = 2,
        user_id: str | None = None,
        debug: bool = False,
    ) -> str:
        return self._run(topic, style, duration, audience, density, perspective_count, user_id, debug=debug)
