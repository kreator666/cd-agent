"""脱口秀创作 Skill —— 按模板规范输出。

基于 data/write-output/standup-template.md 的规范进行创作。
"""

from pathlib import Path

from typing import ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory
from comedy_agent.core.config import settings


# 加载创作模板
_TEMPLATE_PATH = Path(settings.data_dir).parent / "data" / "write-output" / "standup-template.md"
_STANDUP_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8") if _TEMPLATE_PATH.exists() else ""

# 终稿模式硬约束——覆盖模板中要求输出分析过程的指令
_OUTPUT_CONSTRAINT = (
    "【最终输出约束——覆盖上述所有格式要求】\n"
    "你只允许输出段子正文，适合演员直接上台表演的内容。\n"
    "严禁输出以下任何内容：主题、人设、核心观点、使用的喜剧机制、爆点分析。\n"
    "严禁输出分析过程、思考步骤、meta说明、创作思路。\n"
    "严禁使用 Markdown 标题（如 ##）来划分输出结构。\n"
    "输出必须是连续、干净的纯文本段落，不含任何结构标签。"
)

# Debug 模式说明
_DEBUG_NOTE = (
    "【Debug 模式】\n"
    "请输出完整的创作分析过程，包括：主题分析、人设设计、核心观点、\n"
    "使用的喜剧机制、爆点分析、创作思路。\n"
    "分析过程放在正文之前，用【分析过程】和【正文】两个标签分隔。"
)


class StandupArgs(BaseModel):
    """脱口秀创作参数 Schema。"""

    topic: str = Field(description="脱口秀主题，如'职场加班'、'相亲经历'")
    style: str = Field(default="日常观察", description="表演风格：日常观察/自嘲/社会讽刺/职场")
    duration: int = Field(default=3, description="预计时长（分钟），决定篇幅")
    audience: str = Field(default="通用", description="目标受众：通用/年轻人/中年人/特定行业")
    density: str = Field(default="标准", description="笑点密度：密集/标准/稀疏")
    perspective_count: int = Field(default=2, description="多视角版本数量（2-3）")
    debug: bool = Field(default=False, description="Debug 模式：True 时输出分析过程，False 时只输出正文")


class StandupSkill(ComedySkill):
    """脱口秀段子生成器。

    基于 standup-template.md 规范输出，包含预期违背、反逻辑、角色视角。
    """

    task_type: str = "creative"
    name: str = "standup_generator"
    available_styles: ClassVar[list[str]] = ["日常观察", "自嘲", "社会讽刺", "职场", "黑色幽默", "吐槽", "意辰"]
    description: str = (
        "创作脱口秀段子。输入主题、风格、时长、受众，"
        "输出基于脱口秀输出模板 v2 的段子，包含预期违背、反逻辑、角色视角。"
    )
    args_schema: type[BaseModel] = StandupArgs

    SYSTEM_PROMPT: str = _STANDUP_TEMPLATE

    def _build_user_prompt(
        self, topic: str, style: str, duration: int, audience: str, density: str, perspective_count: int, debug: bool = False
    ) -> str:
        return (
            f"请创作一段关于「{topic}」的脱口秀段子。\n\n"
            f"要求：\n"
            f"- 风格：{style}\n"
            f"- 时长：约{duration}分钟\n"
            f"- 受众：{audience}观众\n"
            f"- 笑点密度：{density}"
        )

    def _run(
        self,
        topic: str,
        style: str = "日常观察",
        duration: int = 3,
        audience: str = "通用",
        density: str = "标准",
        perspective_count: int = 2,
        user_id: str | None = None,
        debug: bool = False,
    ) -> str:
        docs = self._retrieve_knowledge(topic, user_id, kind="standup", style=style)
        knowledge_text = self._format_knowledge(docs)
        system_prompt = self.SYSTEM_PROMPT
        if debug:
            system_prompt += "\n\n" + _DEBUG_NOTE
        else:
            system_prompt += "\n\n" + _OUTPUT_CONSTRAINT
        if knowledge_text:
            system_prompt += f"\n\n{knowledge_text}"
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", self._build_user_prompt(topic, style, duration, audience, density, perspective_count, debug=debug)),
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
        user_id: str | None = None,
        debug: bool = False,
    ) -> str:
        return self._run(topic, style, duration, audience, density, perspective_count, user_id, debug=debug)
