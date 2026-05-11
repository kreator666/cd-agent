"""相声创作 Skill —— 传统与新相声剧本生成。"""

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class CrosstalkArgs(BaseModel):
    """相声创作参数 Schema。"""

    topic: str = Field(description="相声主题，如'职场关系'、'科技进步'")
    style: str = Field(default="新相声", description="风格：传统相声/新相声")
    length: str = Field(default="中等", description="篇幅：短(5分钟)/中等(10分钟)/长(15分钟)")
    characters: str = Field(
        default="逗哏活泼、捧哏稳重",
        description="逗哏与捧哏的角色性格设定",
    )


class CrosstalkSkill(ComedySkill):
    """相声剧本生成器。

    输入主题与风格要求，输出包含铺垫、包袱、抖包袱的完整相声剧本。
    """

    task_type: str = "creative"
    name: str = "crosstalk_generator"
    description: str = (
        "创作相声剧本。输入主题、风格、篇幅、角色设定，"
        "输出包含垫话、包袱、抖包袱的完整相声对白。"
    )
    args_schema: type[BaseModel] = CrosstalkArgs

    SYSTEM_PROMPT: str = (
        "你是一位资深相声编剧，精通传统相声的'说学逗唱'与新相声的创新表达。\n"
        "创作原则：\n"
        "- 垫话要自然引入主题，让观众进入情境\n"
        "- 包袱要有逻辑铺垫，三翻四抖是经典手法\n"
        "- 逗哏与捧哏的互动要有节奏感，捧哏的'怼'要精准\n"
        "- 语言口语化，适合舞台表演，避免书面语"
    )

    def _build_prompt(
        self, topic: str, style: str, length: str, characters: str
    ) -> str:
        return (
            f"请创作一段关于「{topic}」的相声剧本。\n\n"
            f"要求：\n"
            f"- 风格：{style}\n"
            f"- 篇幅：{length}\n"
            f"- 角色设定：{characters}\n\n"
            f"结构要求：\n"
            f"1. 垫话：自然引入主题，建立人物关系\n"
            f"2. 正活：2-3个递进式包袱，每个包袱包含铺垫+抖包袱\n"
            f"3. 底：收尾有力，可以是反转或总结式笑点\n\n"
            f"格式要求：用【逗哏】和【捧哏】标注对白，"
            f"包袱处用（包袱）标注，抖包袱处用（抖）标注。\n\n"
            f"请直接输出剧本内容。"
        )

    def _run(
        self,
        topic: str,
        style: str = "新相声",
        length: str = "中等",
        characters: str = "逗哏活泼、捧哏稳重",
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", self._build_prompt(topic, style, length, characters)),
        ])
        llm = ModelFactory.get_model_with_fallback(task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        return str(result.content) if hasattr(result, "content") else str(result)

    async def _arun(
        self,
        topic: str,
        style: str = "新相声",
        length: str = "中等",
        characters: str = "逗哏活泼、捧哏稳重",
    ) -> str:
        return self._run(topic, style, length, characters)
