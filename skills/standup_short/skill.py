"""短视频爆笑段子 Skill —— 四维度输入生成 30 秒内短视频段子。"""

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
    "你只允许输出段子正文，适合直接对着镜头口播的内容。\n"
    "正文必须遵循 `template.md` 的段落结构：【铺垫】、【升级】、【爆梗】、【收尾】。\n"
    "正文总字数（不含标签）约 100~150 字，绝不超过 180 字，按正常语速 30 秒内可以念完。\n"
    "只用 1 个主爆梗，或 2~3 个连续小梗；剧情线必须完整：铺垫 →（升级）→ 爆点/反转 → 收尾。\n"
    "严禁输出分析过程、主题说明、创作思路、爆点分析、meta说明。"
)

# Debug 模式说明
_DEBUG_NOTE = (
    "【Debug 模式】\n"
    "请输出完整的创作分析过程，包括：核心反差设计、铺垫策略、\n"
    "使用的喜剧机制、爆点分析、字数检查。\n"
    "分析过程放在正文之前，用【分析过程】和【正文】两个标签分隔。"
)


class StandupShortArgs(BaseModel):
    """短视频段子创作参数 Schema。"""

    topic: str = Field(description="段子话题")
    attitude: str = Field(description="创作者对话题的态度，如讽刺/自嘲/观察/批判/温情")
    bias: str = Field(description="可能存在的认知偏见或刻板印象，没有则写'无'")
    emotion: str = Field(description="目标情绪基调，如愤怒/荒诞/尴尬/温暖/无奈")
    duration: int = Field(default=3, description="预计时长（分钟），短视频固定30秒内，此参数忽略")


class StandupShortSkill(ComedySkill):
    """短视频爆笑段子生成器。

    基于四维度输入（话题/态度/偏见/情绪）生成 30 秒内的短视频口播段子，
    按【铺垫】→【升级】→【爆梗】→【收尾】固定结构输出。
    """

    task_type: str = "creative"
    name: str = "standup_short"
    available_styles: ClassVar[list[str]] = ["日常观察", "自嘲", "社会讽刺", "职场", "黑色幽默", "吐槽"]
    description: str = (
        "创作 30 秒内短视频爆笑段子。输入话题、态度、偏见、情绪（时长参数可接受但忽略），"
        "按【铺垫】→【升级】→【爆梗】→【收尾】结构输出 100~150 字口播正文。"
    )
    args_schema: type[BaseModel] = StandupShortArgs

    SYSTEM_PROMPT: str = (
        _meta.system_prompt
        if _meta and _meta.system_prompt
        else "你是一位顶级中文短视频喜剧编剧，专写 30 秒内让人笑出声的口播段子。"
    )

    def _build_user_prompt(
        self, topic: str, attitude: str, bias: str, emotion: str, duration: int
    ) -> str:
        template = (
            _meta.prompt_template
            if _meta and _meta.prompt_template
            else (
                "请创作一个关于「{topic}」的短视频爆笑段子，30 秒以内。\n\n"
                "四维度输入：\n"
                "- 态度：{attitude}\n"
                "- 偏见注意：{bias}\n"
                "- 情绪基调：{emotion}\n\n"
                "时长固定 30 秒以内，输入的时长参数忽略。\n"
                "请严格围绕以上话题和四维度创作，不要偏离主题。"
            )
        )
        return template.format(
            topic=topic, attitude=attitude, bias=bias, emotion=emotion
        )

    def _run(
        self,
        topic: str,
        attitude: str,
        bias: str,
        emotion: str,
        duration: int = 3,
        user_id: str | None = None,
        debug: bool = False,
    ) -> str:
        docs = self._retrieve_knowledge(topic, user_id, kind="standup", style="日常观察")
        knowledge_text = self._format_knowledge(docs)
        system_prompt = self.SYSTEM_PROMPT
        if debug:
            system_prompt += "\n\n" + _DEBUG_NOTE
        else:
            system_prompt += "\n\n" + _OUTPUT_CONSTRAINT
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
        attitude: str,
        bias: str,
        emotion: str,
        duration: int = 3,
        user_id: str | None = None,
        debug: bool = False,
    ) -> str:
        return self._run(
            topic=topic,
            attitude=attitude,
            bias=bias,
            emotion=emotion,
            duration=duration,
            user_id=user_id,
            debug=debug,
        )
