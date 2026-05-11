"""情景喜剧 Skill —— 单集剧本大纲与对白生成。"""

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class SitcomArgs(BaseModel):
    """情景喜剧创作参数 Schema。"""

    scenario: str = Field(
        description="情景设定，如'合租公寓'、'创业公司'、'小餐馆'",
    )
    episode_theme: str = Field(description="本集主题，如'室友带对象回家'、'老板突然查岗'")
    characters: str = Field(
        default="",
        description="常驻角色列表及性格，如'张伟(抠门)、李梅(洁癖)、王强(宅男)'",
    )
    scenes: int = Field(default=3, description="场景数量（2-5个）")


class SitcomSkill(ComedySkill):
    """情景喜剧单集生成器。

    输入情景设定、本集主题和角色信息，输出单集剧本大纲与关键对白。
    """

    task_type: str = "creative"
    name: str = "sitcom_generator"
    description: str = (
        "创作情景喜剧单集剧本。输入情景设定、本集主题、角色、场景数，"
        "输出包含大纲和关键对白的完整单集剧本。"
    )
    args_schema: type[BaseModel] = SitcomArgs

    SYSTEM_PROMPT: str = (
        "你是一位资深情景喜剧编剧，熟悉《老友记》《生活大爆炸》《爱情公寓》等经典结构。\n"
        "创作原则：\n"
        "- A/B 线并行：主故事线+副故事线交织，结尾交汇\n"
        "- 角色声音鲜明：每个角色的说话方式要有辨识度\n"
        "- 笑点来自关系：最好的笑点是角色互动中的化学反应\n"
        "- 场景转换简洁：用动作或台词自然过渡，避免生硬换场\n"
        "- 结尾要有 callback：呼应本集早期的某个细节"
    )

    def _build_prompt(
        self, scenario: str, episode_theme: str, characters: str, scenes: int
    ) -> str:
        char_info = f"\n常驻角色：{characters}\n" if characters else ""
        return (
            f"请创作一集情景喜剧剧本。\n\n"
            f"情景设定：{scenario}{char_info}"
            f"本集主题：{episode_theme}\n"
            f"场景数量：{scenes}个\n\n"
            f"结构要求：\n"
            f"1. 冷开场（可选）：30秒内建立本集基调\n"
            f"2. 主故事线（A线）：核心冲突的发展与解决\n"
            f"3. 副故事线（B线）：与A线平行，结尾交汇\n"
            f"4. 结尾场景：A/B线交汇，callback 收尾\n\n"
            f"格式要求：\n"
            f"- 先给出200字以内的大纲\n"
            f"- 再给出完整剧本，用角色名标注对白\n"
            f"- 场景切换用[场景：地点]标注\n\n"
            f"请直接输出剧本内容。"
        )

    def _run(
        self,
        scenario: str,
        episode_theme: str,
        characters: str = "",
        scenes: int = 3,
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", self._build_prompt(scenario, episode_theme, characters, scenes)),
        ])
        llm = ModelFactory.get_model(task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        return str(result.content) if hasattr(result, "content") else str(result)

    async def _arun(
        self,
        scenario: str,
        episode_theme: str,
        characters: str = "",
        scenes: int = 3,
    ) -> str:
        return self._run(scenario, episode_theme, characters, scenes)
