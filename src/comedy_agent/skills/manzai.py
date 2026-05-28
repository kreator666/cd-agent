"""漫才创作 Skill —— 按模板规范输出。

基于 data/write-output/manzai-template.md 的规范进行创作。
"""

from pathlib import Path

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory
from comedy_agent.core.config import settings


_TEMPLATE_PATH = Path(settings.data_dir).parent / "data" / "write-output" / "manzai-template.md"
_MANZAI_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8") if _TEMPLATE_PATH.exists() else ""


class ManzaiArgs(BaseModel):
    """漫才创作参数 Schema。"""

    topic: str = Field(description="漫才话题，如'职场加班'、'相亲经历'")
    duration: int = Field(default=5, description="预计时长（分钟），决定篇幅")
    segments_count: int = Field(default=3, description="段落数量（话题切换次数）")
    absurd_level: str = Field(default="标准", description="荒谬等级：轻微/标准/极致")


class ManzaiSkill(ComedySkill):
    """漫才剧本生成器。

    基于 manzai-template.md 规范输出，核心是搭档配合 + 连续否定 + 节奏堆叠。
    """

    task_type: str = "creative"
    name: str = "manzai_generator"
    description: str = (
        "创作漫才剧本。输入话题和时长，"
        "输出基于漫才输出模板的完整对白，包含连续否定、节奏设计、反差收尾。"
    )
    args_schema: type[BaseModel] = ManzaiArgs

    SYSTEM_PROMPT: str = (
        "你是一位资深漫才编剧。\n\n"
        + _MANZAI_TEMPLATE
        + "\n\n"
        "创作时严格按照上述模板规范执行，输出干净的漫才对白（不含结构标签）。"
    )

    def _build_prompt(self, topic: str, duration: int, segments_count: int, absurd_level: str) -> str:
        return (
            f"请创作一段关于「{topic}」的漫才剧本。\n\n"
            f"要求：\n"
            f"- 时长：约{duration}分钟\n"
            f"- 段落数量：{segments_count}段（话题切换次数）\n"
            f"- 荒谬等级：{absurd_level}\n\n"
            f"输出要求：\n"
            f"1. 正文不含【结构标签】，只输出干净的对白\n"
            f"2. 用（上）和（下）标注角色对白\n"
            f"3. 包含三次否定，理由逐级荒谬\n"
            f"4. 节奏密集，每30-60秒一个笑点\n"
            f"5. 结尾使用突然恢复正常的反差收尾"
        )

    def _run(
        self,
        topic: str,
        duration: int = 5,
        segments_count: int = 3,
        absurd_level: str = "标准",
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", self._build_prompt(topic, duration, segments_count, absurd_level)),
        ])
        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        return str(result.content) if hasattr(result, "content") else str(result)

    async def _arun(
        self,
        topic: str,
        duration: int = 5,
        segments_count: int = 3,
        absurd_level: str = "标准",
    ) -> str:
        return self._run(topic, duration, segments_count, absurd_level)
