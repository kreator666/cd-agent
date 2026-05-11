"""剧本评估 Skill —— 多维度喜剧剧本质量评分与改进建议。"""

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class ScriptEvaluatorArgs(BaseModel):
    """剧本评估参数 Schema。"""

    script: str = Field(description="要评估的完整剧本内容")
    criteria: str = Field(
        default="全部维度",
        description=(
            "评估维度：笑点密度/角色塑造/结构完整性/口语化程度/"
            "表演可行性/情感共鸣/全部维度"
        ),
    )


class ScriptEvaluatorSkill(ComedySkill):
    """喜剧剧本质量评估工具。

    输入完整剧本，按多维度评分并给出可执行的改进建议。
    """

    task_type: str = "analytical"
    name: str = "script_evaluator"
    description: str = (
        "评估喜剧剧本质量。输入剧本内容，按笑点密度、角色塑造、"
        "结构完整性、口语化程度等维度评分并给出改进建议。"
    )
    args_schema: type[BaseModel] = ScriptEvaluatorArgs

    SYSTEM_PROMPT: str = (
        "你是一位资深喜剧导演兼编剧顾问，拥有丰富的剧本评估经验。\n"
        "评估原则：\n"
        "- 笑点密度：每分钟有效笑点的数量及分布是否合理\n"
        "- 角色塑造：角色是否有鲜明个性，对白是否符合人设\n"
        "- 结构完整性：起承转合是否完整，高潮是否到位\n"
        "- 口语化程度：对白是否自然，是否适合舞台表演\n"
        "- 表演可行性：场景转换是否过于复杂，道具需求是否合理\n"
        "- 情感共鸣：笑料是否建立在观众能共鸣的生活经验上\n"
        "- 评分标准：每项满分10分，给出具体理由"
    )

    def _build_prompt(self, script: str, criteria: str) -> str:
        return (
            f"请对以下喜剧剧本进行评估（评估维度：{criteria}）。\n\n"
            f"剧本内容：\n```\n{script}\n```\n\n"
            f"评估要求：\n"
            f"1. 逐项评分：笑点密度 / 角色塑造 / 结构完整性 / 口语化程度 / 表演可行性 / 情感共鸣\n"
            f"   （每项满分10分，注明权重）\n"
            f"2. 综合评分：加权总分（满分10分）\n"
            f"3. 优点总结：剧本最值得保留的2-3个亮点\n"
            f"4. 问题诊断：当前最明显的2-3个问题\n"
            f"5. 改进建议：针对每个问题给出具体的修改方案\n"
            f"6. 参考案例：可以借鉴哪部经典作品的类似处理手法\n\n"
            f"请输出结构化的评估报告。"
        )

    def _run(
        self,
        script: str,
        criteria: str = "全部维度",
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", self._build_prompt(script, criteria)),
        ])
        llm = ModelFactory.get_model_with_fallback(task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        return str(result.content) if hasattr(result, "content") else str(result)

    async def _arun(
        self,
        script: str,
        criteria: str = "全部维度",
    ) -> str:
        return self._run(script, criteria)
