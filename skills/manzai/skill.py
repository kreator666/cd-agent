"""漫才创作 Skill —— 按模板规范输出。"""

import sys
from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


_meta = getattr(sys.modules[__name__], "_skill_meta", None)


class ManzaiArgs(BaseModel):
    """漫才创作参数 Schema。"""

    topic: str = Field(description="漫才话题，如'职场加班'、'相亲经历'")
    style: str = Field(default="传统漫才", description="风格：传统漫才/快节奏漫才/温情漫才/怪诞漫才")
    duration: int = Field(default=5, description="预计时长（分钟），决定篇幅")
    segments_count: int = Field(default=3, description="段落数量（话题切换次数）")
    absurd_level: str = Field(default="标准", description="荒谬等级：轻微/标准/极致")


class ManzaiSkill(ComedySkill):
    """漫才剧本生成器。"""

    task_type: str = "creative"
    name: str = "manzai_generator"
    available_styles: ClassVar[list[str]] = ["传统漫才", "快节奏漫才", "温情漫才", "怪诞漫才"]
    description: str = (
        "创作漫才剧本。输入话题、风格和时长，"
        "输出基于漫才输出模板的完整对白，包含连续否定、节奏设计、反差收尾。"
    )
    args_schema: type[BaseModel] = ManzaiArgs

    SYSTEM_PROMPT: str = (
        _meta.system_prompt
        if _meta and _meta.system_prompt
        else "你是一位资深漫才编剧。创作时严格按照模板规范执行，输出干净的漫才对白（不含结构标签）。"
    )

    def _build_prompt(self, topic: str, style: str, duration: int, segments_count: int, absurd_level: str) -> str:
        template = (
            _meta.prompt_template
            if _meta and _meta.prompt_template
            else (
                "请创作一段关于「{topic}」的漫才剧本。\n\n"
                "要求：\n"
                "- 风格：{style}\n"
                "- 时长：约{duration}分钟\n"
                "- 段落数量：{segments_count}段（话题切换次数）\n"
                "- 荒谬等级：{absurd_level}\n\n"
                "输出要求：\n"
                "1. 正文不含【结构标签】，只输出干净的对白\n"
                "2. 用（上）和（下）标注角色对白\n"
                "3. 包含三次否定，理由逐级荒谬\n"
                "4. 节奏密集，每30-60秒一个笑点\n"
                "5. 结尾使用突然恢复正常的反差收尾"
            )
        )
        return template.format(
            topic=topic, style=style, duration=duration,
            segments_count=segments_count, absurd_level=absurd_level
        )

    def _run(
        self,
        topic: str,
        style: str = "传统漫才",
        duration: int = 5,
        segments_count: int = 3,
        absurd_level: str = "标准",
        user_id: str | None = None,
    ) -> str:
        docs = self._retrieve_knowledge(topic, user_id, kind="manzai")
        knowledge_text = self._format_knowledge(docs)
        system_prompt = self.SYSTEM_PROMPT
        if knowledge_text:
            system_prompt += f"\n\n{knowledge_text}"
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", self._build_prompt(topic, style, duration, segments_count, absurd_level)),
        ])
        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        return str(result.content) if hasattr(result, "content") else str(result)

    async def _arun(
        self,
        topic: str,
        style: str = "传统漫才",
        duration: int = 5,
        segments_count: int = 3,
        absurd_level: str = "标准",
        user_id: str | None = None,
    ) -> str:
        return self._run(topic, style, duration, segments_count, absurd_level, user_id)
