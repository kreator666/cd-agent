"""笑点分析 Skill —— 喜剧文本结构与节奏分析工具。"""

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class JokeAnalyzerArgs(BaseModel):
    """笑点分析参数 Schema。"""

    content: str = Field(description="要分析的喜剧文本内容")
    analysis_type: str = Field(
        default="综合分析",
        description="分析维度：结构分析/节奏分析/预期违背分析/语言技巧分析/综合分析",
    )


class JokeAnalyzerSkill(ComedySkill):
    """喜剧文本分析工具。

    输入喜剧段子或剧本片段，输出专业的笑点结构分析报告。
    """

    name: str = "joke_analyzer"
    description: str = (
        "分析喜剧文本的笑点结构与创作技巧。输入喜剧内容，"
        "输出包含结构拆解、节奏评估、预期违背分析等专业报告。"
    )
    args_schema: type[BaseModel] = JokeAnalyzerArgs

    SYSTEM_PROMPT: str = (
        "你是一位喜剧理论专家，精通喜剧结构学、笑理学和表演节奏分析。\n"
        "分析原则：\n"
        "- 结构分析：识别铺垫(Setup)、升级(Escalation)、反转(Twist)、Callback\n"
        "- 节奏分析：评估信息密度、停顿位置、节奏快慢变化\n"
        "- 预期违背：分析如何建立预期、如何打破预期、违背的合理性\n"
        "- 语言技巧：识别谐音、双关、比喻、夸张、排比等修辞手法\n"
        "- 评估要客观：既指出优点，也给出可改进之处"
    )

    def _build_prompt(self, content: str, analysis_type: str) -> str:
        return (
            f"请对以下喜剧文本进行「{analysis_type}」。\n\n"
            f"文本内容：\n```\n{content}\n```\n\n"
            f"分析要求：\n"
            f"1. 整体结构：文本的整体喜剧架构是什么\n"
            f"2. 笑点拆解：逐个分析每个笑点的构成要素\n"
            f"3. 节奏评估：信息投放的节奏是否合理\n"
            f"4. 优点总结：这段文本最成功的2-3个点\n"
            f"5. 改进建议：如果由你来改，会调整哪些地方\n\n"
            f"请用专业但易懂的语言输出分析报告。"
        )

    def _run(
        self,
        content: str,
        analysis_type: str = "综合分析",
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", self._build_prompt(content, analysis_type)),
        ])
        llm = ModelFactory.get_model()
        chain = prompt | llm
        result = chain.invoke({})
        return str(result.content) if hasattr(result, "content") else str(result)

    async def _arun(
        self,
        content: str,
        analysis_type: str = "综合分析",
    ) -> str:
        return self._run(content, analysis_type)
