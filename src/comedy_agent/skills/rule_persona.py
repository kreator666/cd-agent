"""人物画像 Rule Skill —— 将写作规则注入系统提示。

根据人物画像的结构化规则约束，对生成内容进行约束和校验。
"""

from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory


class RulePersonaArgs(BaseModel):
    """人物画像规则参数 Schema。"""

    outline: str = Field(description="创意大纲或场景描述")
    rule_content: dict = Field(description="结构化写作规则约束 JSON")


class RulePersonaSkill(ComedySkill):
    """人物画像规则注入器。

    根据结构化写作规则约束，对生成内容进行约束。
    """

    task_type: str = "creative"
    name: str = "rule_persona"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "人物画像规则约束。输入创意大纲和规则 JSON，"
        "输出严格遵循该规则约束的剧本内容。"
    )
    args_schema: type[BaseModel] = RulePersonaArgs

    def _format_rules(self, rule_content: dict) -> str:
        lines: list[str] = []
        if rule_content.get("prefer_short_sentence"):
            lines.append("- 每句话不超过 15 个字，使用短句节奏。")
        if rule_content.get("forbidden_words"):
            words = ", ".join(rule_content["forbidden_words"])
            lines.append(f"- 禁用词汇：{words}")
        pace = rule_content.get("sentence_pace")
        if pace:
            lines.append(f"- 句子节奏：{pace}")
        if rule_content.get("opening_hook"):
            lines.append("- 开头必须有钩子，立即抓住注意力。")
        example = rule_content.get("example_style")
        if example:
            lines.append(f"- 风格示例参考：\n{example}")
        return "\n".join(lines) if lines else "- 无特殊规则约束。"

    def _run(
        self,
        outline: str,
        rule_content: dict,
        user_id: str | None = None,
    ) -> str:
        rules_text = self._format_rules(rule_content)
        system_prompt = (
            "你是一位严格遵守人物画像规则的剧本助手。\n"
            "请根据以下写作规则约束生成内容，必须严格遵守每一条规则：\n"
            f"{rules_text}\n\n"
            "输出要求：只输出最终剧本内容，不要添加解释。"
        )
        human_prompt = f"创意大纲：\n{outline}\n\n请生成严格遵循上述规则的剧本内容。"
        # 规则内容/大纲中可能包含 JSON 花括号，需转义为字面量，避免被 ChatPromptTemplate 当变量解析
        system_prompt = system_prompt.replace("{", "{{").replace("}", "}}")
        human_prompt = human_prompt.replace("{", "{{").replace("}", "}}")
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_prompt),
        ])
        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        if hasattr(result, "content"):
            return str(result.content)
        return str(result)

    async def _arun(
        self,
        outline: str,
        rule_content: dict,
        user_id: str | None = None,
    ) -> str:
        return self._run(outline, rule_content, user_id=user_id)
