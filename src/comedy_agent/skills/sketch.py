"""小品创作 Skill —— 短剧剧本生成。"""

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class SketchArgs(BaseModel):
    """小品创作参数 Schema。"""

    theme: str = Field(description="小品主题，如'家庭聚餐'、'面试遭遇'")
    characters_count: int = Field(default=3, description="角色数量（2-5人）")
    setting: str = Field(default="家庭", description="场景设定：家庭/职场/校园/医院/公共场合")
    duration: int = Field(default=8, description="预计时长（分钟），决定篇幅")


class SketchSkill(ComedySkill):
    """小品剧本生成器。

    输入主题、角色数、场景和时长，输出包含场景描述、对白和笑点的完整小品剧本。
    """

    name: str = "sketch_generator"
    description: str = (
        "创作小品剧本。输入主题、角色数、场景、时长，"
        "输出包含场景描述、角色对白、冲突与笑点的完整剧本。"
    )
    args_schema: type[BaseModel] = SketchArgs

    SYSTEM_PROMPT: str = (
        "你是一位资深小品编剧，擅长创作结构紧凑、笑中带泪的短剧剧本。\n"
        "创作原则：\n"
        "- 开场要快：30秒内让观众明白人物关系和情境\n"
        "- 冲突要真：基于生活中的真实矛盾，夸张但不失真\n"
        "- 笑点要密：每1-2分钟至少一个有效笑点\n"
        "- 结尾要收：可以有反转、温情或留白，但不能拖沓\n"
        "- 对白要口语化，避免朗诵腔"
    )

    def _build_prompt(
        self, theme: str, characters_count: int, setting: str, duration: int
    ) -> str:
        return (
            f"请创作一段关于「{theme}」的小品剧本。\n\n"
            f"要求：\n"
            f"- 角色数量：{characters_count}人\n"
            f"- 场景设定：{setting}\n"
            f"- 时长：约{duration}分钟\n\n"
            f"结构要求：\n"
            f"1. 角色介绍：列出每个角色的名字和性格特点\n"
            f"2. 场景描述：交代时间、地点、背景\n"
            f"3. 正戏：围绕核心冲突展开，包含2-3次误会或反转\n"
            f"4. 高潮：矛盾爆发，笑点最密集\n"
            f"5. 结尾：巧妙收束，可以是反转、和解或开放式\n\n"
            f"格式要求：用角色名标注对白，场景切换用[场景]标注。\n\n"
            f"请直接输出剧本内容。"
        )

    def _run(
        self,
        theme: str,
        characters_count: int = 3,
        setting: str = "家庭",
        duration: int = 8,
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", self._build_prompt(theme, characters_count, setting, duration)),
        ])
        llm = ModelFactory.get_model()
        chain = prompt | llm
        result = chain.invoke({})
        return str(result.content) if hasattr(result, "content") else str(result)

    async def _arun(
        self,
        theme: str,
        characters_count: int = 3,
        setting: str = "家庭",
        duration: int = 8,
    ) -> str:
        return self._run(theme, characters_count, setting, duration)
