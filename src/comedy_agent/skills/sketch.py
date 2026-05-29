"""小品创作 Skill —— 按模板规范输出。

基于 data/write-output/sketch-template.md 的规范进行创作。
"""

from pathlib import Path

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory
from comedy_agent.core.config import settings


_TEMPLATE_PATH = Path(settings.data_dir).parent / "data" / "write-output" / "sketch-template.md"
_SKETCH_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8") if _TEMPLATE_PATH.exists() else ""


class SketchArgs(BaseModel):
    """小品创作参数 Schema。"""

    theme: str = Field(description="小品主题，如'家庭聚餐'、'面试遭遇'")
    characters_count: int = Field(default=3, description="角色数量（2-5人）")
    setting: str = Field(default="家庭", description="场景设定：家庭/职场/校园/医院/公共场合")
    duration: int = Field(default=8, description="预计时长（分钟），决定篇幅")
    conflict_type: str = Field(default="执念vs现实", description="冲突类型：执念vs现实/执念vs执念/信息差")


class SketchSkill(ComedySkill):
    """小品剧本生成器。

    基于 sketch-template.md 规范输出，核心是角色冲突 + 情境升级 + 弹簧魔鬼/雪球效应。
    """

    task_type: str = "creative"
    name: str = "sketch_generator"
    description: str = (
        "创作小品剧本。输入主题、角色数、场景、时长，"
        "输出基于小品输出模板的完整剧本，包含角色执念、冲突升级、肢体喜剧。"
    )
    args_schema: type[BaseModel] = SketchArgs

    SYSTEM_PROMPT: str = (
        "你是一位资深小品编剧。\n\n"
        + _SKETCH_TEMPLATE
        + "\n\n"
        "创作时严格按照上述模板规范执行，输出干净的小品剧本（不含结构标签）。"
    )

    def _build_prompt(
        self, theme: str, characters_count: int, setting: str, duration: int, conflict_type: str
    ) -> str:
        return (
            f"请创作一段关于「{theme}」的小品剧本。\n\n"
            f"要求：\n"
            f"- 角色数量：{characters_count}人\n"
            f"- 场景设定：{setting}\n"
            f"- 时长：约{duration}分钟\n"
            f"- 冲突类型：{conflict_type}\n\n"
            f"输出要求：\n"
            f"1. 正文不含【结构标签】，只输出干净的小品剧本\n"
            f"2. 每个主要角色有一个核心执念（机械僵硬的核心）\n"
            f"3. 冲突设计使用弹簧魔鬼或雪球效应手法\n"
            f"4. 包含肢体喜剧设计（标志性动作、道具喜剧、走位调度）\n"
            f"5. 用角色名标注对白，场景切换用[场景]标注"
        )

    def _run(
        self,
        theme: str,
        characters_count: int = 3,
        setting: str = "家庭",
        duration: int = 8,
        conflict_type: str = "执念vs现实",
        user_id: str | None = None,
    ) -> str:
        docs = self._retrieve_knowledge(theme, user_id, kind="sketch")
        knowledge_text = self._format_knowledge(docs)
        system_prompt = self.SYSTEM_PROMPT
        if knowledge_text:
            system_prompt += f"\n\n{knowledge_text}"
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", self._build_prompt(theme, characters_count, setting, duration, conflict_type)),
        ])
        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        return str(result.content) if hasattr(result, "content") else str(result)

    async def _arun(
        self,
        theme: str,
        characters_count: int = 3,
        setting: str = "家庭",
        duration: int = 8,
        conflict_type: str = "执念vs现实",
        user_id: str | None = None,
    ) -> str:
        return self._run(theme, characters_count, setting, duration, conflict_type, user_id)
