"""脱口秀创作 Skill —— 按模板规范输出。

基于 data/write-output/standup-template.md 的规范进行创作。
"""

from pathlib import Path

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory
from comedy_agent.core.config import settings


# 加载模板文件
_TEMPLATE_PATH = Path(settings.data_dir).parent / "data" / "write-output" / "standup-template.md"
_STANDUP_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8") if _TEMPLATE_PATH.exists() else ""


class StandupArgs(BaseModel):
    """脱口秀创作参数 Schema。"""

    topic: str = Field(description="脱口秀主题，如'职场加班'、'相亲经历'")
    style: str = Field(default="日常观察", description="表演风格：日常观察/自嘲/社会讽刺/职场")
    duration: int = Field(default=3, description="预计时长（分钟），决定篇幅")
    audience: str = Field(default="通用", description="目标受众：通用/年轻人/中年人/特定行业")
    density: str = Field(default="标准", description="笑点密度：密集/标准/稀疏")
    perspective_count: int = Field(default=2, description="多视角版本数量（2-3）")


class StandupSkill(ComedySkill):
    """脱口秀段子生成器。

    基于 standup-template.md 规范输出，包含预期违背、反逻辑、角色视角、多视角选择。
    """

    task_type: str = "creative"
    name: str = "standup_generator"
    description: str = (
        "创作脱口秀段子。输入主题、风格、时长、受众，"
        "输出基于脱口秀输出模板 v2 的段子，包含预期违背、反逻辑、角色视角。"
    )
    args_schema: type[BaseModel] = StandupArgs

    SYSTEM_PROMPT: str = (
        "你是一位资深脱口秀编剧。\n\n"
        + _STANDUP_TEMPLATE
        + "\n\n"
        "创作时严格按照上述模板规范执行，输出干净的脱口秀文本（不含结构标签）。"
    )

    def _build_user_prompt(self, topic: str, style: str, duration: int, audience: str, density: str, perspective_count: int) -> str:
        return (
            f"请创作一段关于「{topic}」的脱口秀段子。\n\n"
            f"要求：\n"
            f"- 风格：{style}\n"
            f"- 时长：约{duration}分钟\n"
            f"- 受众：{audience}观众\n"
            f"- 笑点密度：{density}\n\n"
            f"输出要求：\n"
            f"1. 正文不含【结构标签】，只输出干净的脱口秀文本\n"
            f"2. 包含 {perspective_count} 个不同视角的版本供选择（自嘲式/愤怒式/荒诞式）\n"
            f"3. 每个笑点标注手法类型（预期违背/反逻辑/Call Back 等）\n"
            f"4. 结尾有自然 Call Back"
        )

    def _run(
        self,
        topic: str,
        style: str = "日常观察",
        duration: int = 3,
        audience: str = "通用",
        density: str = "标准",
        perspective_count: int = 2,
    ) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            ("human", self._build_user_prompt(topic, style, duration, audience, density, perspective_count)),
        ])
        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        chain = prompt | llm
        result = chain.invoke({})
        if hasattr(result, "content"):
            return str(result.content)
        return str(result)

    async def _arun(
        self,
        topic: str,
        style: str = "日常观察",
        duration: int = 3,
        audience: str = "通用",
        density: str = "标准",
        perspective_count: int = 2,
    ) -> str:
        return self._run(topic, style, duration, audience, density, perspective_count)
