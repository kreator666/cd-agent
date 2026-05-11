"""脱口秀创作 Skill —— 首个 MVP Skill。

验证 Tool → Prompt → LLM → Output 最小闭环。
"""

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class StandupArgs(BaseModel):
    """脱口秀创作参数 Schema。"""

    topic: str = Field(description="脱口秀主题，如'职场加班'、'相亲经历'")
    style: str = Field(default="日常观察", description="表演风格：日常观察/自嘲/社会讽刺/职场")
    duration: int = Field(default=3, description="预计时长（分钟），决定篇幅")
    audience: str = Field(default="通用", description="目标受众：通用/年轻人/中年人/特定行业")


class StandupSkill(ComedySkill):
    """脱口秀段子生成器。

    输入主题与风格要求，输出结构完整的脱口秀段子，
    包含开场钩子、递进式笑点、Callback 闭环。
    """

    task_type: str = "creative"
    name: str = "standup_generator"
    description: str = (
        "创作脱口秀段子。输入主题、风格、时长、受众，"
        "输出结构完整的脱口秀段子，包含开场、主体、callback。"
    )
    args_schema: type[BaseModel] = StandupArgs

    # ------------------------------------------------------------------ #
    # Prompt 工程
    # ------------------------------------------------------------------ #
    SYSTEM_PROMPT: str = (
        "你是一位资深脱口秀编剧，擅长创作结构完整、笑点密集的脱口秀段子。\n"
        "创作原则：\n"
        "- 铺垫要足够让观众产生预期\n"
        "- 反转要打破预期但不突兀\n"
        "- Callback 结尾要自然呼应开头\n"
        "- 语言口语化，适合口头表演"
    )

    def _build_prompt(self, topic: str, style: str, duration: int, audience: str) -> str:
        """根据参数构建创作 Prompt。"""
        return (
            f"请创作一段关于「{topic}」的脱口秀段子。\n\n"
            f"要求：\n"
            f"- 风格：{style}\n"
            f"- 时长：约{duration}分钟\n"
            f"- 受众：{audience}观众\n\n"
            f"结构要求：\n"
            f"1. 开场钩子：用一句话抓住观众注意力\n"
            f"2. 主体：2-3个递进式笑点，每个笑点包含铺垫+反转\n"
            f"3. Callback：结尾呼应开头，形成闭环\n\n"
            f"请直接输出段子内容，不需要解释结构。"
        )

    # ------------------------------------------------------------------ #
    # 执行
    # ------------------------------------------------------------------ #
    def _run(
        self,
        topic: str,
        style: str = "日常观察",
        duration: int = 3,
        audience: str = "通用",
    ) -> str:
        """同步执行：调用 LLM 生成段子。"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", self._build_prompt(topic, style, duration, audience)),
        ])

        llm = ModelFactory.get_model(task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})

        # 兼容不同 LLM 返回格式（str 或 AIMessage）
        if hasattr(result, "content"):
            return str(result.content)
        return str(result)

    async def _arun(
        self,
        topic: str,
        style: str = "日常观察",
        duration: int = 3,
        audience: str = "通用",
    ) -> str:
        """异步执行：复用同步逻辑。"""
        return self._run(topic, style, duration, audience)
