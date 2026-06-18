"""日式短剧（コント）创作 Skill —— 按模板规范输出。"""

import sys
from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


_meta = getattr(sys.modules[__name__], "_skill_meta", None)


class JapaneseSketchArgs(BaseModel):
    """日式短剧创作参数 Schema。"""

    theme: str = Field(description="短剧主题，如'便利店打工'、'医院看病'")
    style: str = Field(default="经典コント", description="风格：经典コント/黑色幽默/温情喜剧/荒诞喜剧")
    characters_count: int = Field(default=2, description="角色数量（2-3人）")
    setting: str = Field(default="便利店", description="场景设定：便利店/办公室/医院/家里/学校/餐厅")
    duration: int = Field(default=5, description="预计时长（分钟），决定篇幅")
    character_type: str = Field(default="偏执", description="极端性格：偏执/懦弱/自大/较真")
    punchline_density: int = Field(default=4, description="笑点密度（个/分钟），最低4，优秀5，顶级6")


class JapaneseSketchSkill(ComedySkill):
    """日式短剧（コント）剧本生成器。"""

    task_type: str = "creative"
    name: str = "japanese_sketch_generator"
    available_styles: ClassVar[list[str]] = ["经典コント", "黑色幽默", "温情喜剧", "荒诞喜剧"]
    description: str = (
        "创作日式短剧（コント）剧本。输入主题、风格、角色数、场景、时长，"
        "输出基于日式短剧输出模板的完整剧本，包含极端性格、明确目标、阻碍升级。"
    )
    args_schema: type[BaseModel] = JapaneseSketchArgs

    SYSTEM_PROMPT: str = (
        _meta.system_prompt
        if _meta and _meta.system_prompt
        else "你是一位资深日式短剧（コント）编剧。创作时严格按照模板规范执行，输出干净的短剧剧本（不含结构标签）。"
    )

    def _build_prompt(
        self, theme: str, style: str, characters_count: int, setting: str, duration: int, character_type: str, punchline_density: int
    ) -> str:
        template = (
            _meta.prompt_template
            if _meta and _meta.prompt_template
            else (
                "请创作一段关于「{theme}」的日式短剧（コント）剧本。\n\n"
                "要求：\n"
                "- 风格：{style}\n"
                "- 角色数量：{characters_count}人\n"
                "- 场景设定：{setting}\n"
                "- 时长：约{duration}分钟\n"
                "- 主角极端性格：{character_type}\n"
                "- 笑点密度：{punchline_density}个/分钟\n\n"
                "输出要求：\n"
                "1. 正文不含【结构标签】，只输出干净的短剧剧本\n"
                "2. 每个角色有一个极端性格，全程不崩人设\n"
                "3. 角色有一个明确的核心目标\n"
                "4. 阻碍升级三层：初步受阻 → 叠加新矛盾 → 彻底失控\n"
                "5. 笑点密度≥{punchline_density}个/分钟\n"
                "6. 用角色名标注对白，场景切换用[场景]标注\n"
                "7. 每个笑点用 **【笑点N】** 标注，并简要说明笑点来源"
            )
        )
        return template.format(
            theme=theme, style=style, characters_count=characters_count,
            setting=setting, duration=duration, character_type=character_type,
            punchline_density=punchline_density
        )

    def _run(
        self,
        theme: str,
        style: str = "经典コント",
        characters_count: int = 2,
        setting: str = "便利店",
        duration: int = 5,
        character_type: str = "偏执",
        punchline_density: int = 4,
        user_id: str | None = None,
    ) -> str:
        docs = self._retrieve_knowledge(theme, user_id, kind="japanese_sketch")
        knowledge_text = self._format_knowledge(docs)
        system_prompt = self.SYSTEM_PROMPT
        if knowledge_text:
            system_prompt += f"\n\n{knowledge_text}"
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", self._build_prompt(theme, style, characters_count, setting, duration, character_type, punchline_density)),
        ])
        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        return str(result.content) if hasattr(result, "content") else str(result)

    async def _arun(
        self,
        theme: str,
        style: str = "经典コント",
        characters_count: int = 2,
        setting: str = "便利店",
        duration: int = 5,
        character_type: str = "偏执",
        punchline_density: int = 4,
        user_id: str | None = None,
    ) -> str:
        return self._run(theme, style, characters_count, setting, duration, character_type, punchline_density, user_id)
