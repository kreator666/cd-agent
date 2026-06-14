"""排版 Skill —— 将文本转换为指定平台的文章格式。"""

from __future__ import annotations

import logging
from typing import ClassVar

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from comedy_agent.models.factory import ModelFactory
from comedy_agent.skills.base import ComedySkill

logger = logging.getLogger(__name__)


class LayoutArgs(BaseModel):
    """排版参数 Schema。"""

    text: str = Field(description="需要排版的文章内容")
    platform: str = Field(
        default="wechat",
        description="目标平台：wechat（微信公众号）、xiaohongshu（小红书）、zhihu（知乎）、bilibili（B站专栏）",
    )


class LayoutSkill(ComedySkill):
    """平台化排版器。

    将输入文本转换为指定平台（微信公众号、小红书、知乎、B站专栏）的排版格式。
    """

    task_type: str = "creative"
    name: str = "layout"
    available_styles: ClassVar[list[str]] = []
    description: str = (
        "排版工具。将文本内容转换为指定平台的文章格式，如微信公众号、小红书、知乎、B站专栏。"
    )
    args_schema: type[BaseModel] = LayoutArgs

    SYSTEM_PROMPT: str = (
        "你是一位专业的内容排版师。请根据目标平台特性，将输入文本转换为适合该平台发布的格式。\n"
        "规则：\n"
        "1. 不改变原文的核心信息、事实和语义。\n"
        "2. 仅调整标题层级、段落节奏、重点标记、引用块、emoji 等排版元素。\n"
        "3. 输出可直接复制到对应平台编辑器中的 Markdown 文本。\n"
        "4. 不要输出任何解释，只输出排版后的内容。"
    )

    # 各平台排版风格补充说明
    PLATFORM_NOTES: ClassVar[dict[str, str]] = {
        "wechat": "微信公众号风格：使用清晰的二级/三级标题、重点加粗、引用块、分隔线，段落适中，适合手机阅读。",
        "xiaohongshu": "小红书风格：短段落、多 emoji、分段标签、口语化标题，强调视觉冲击和互动感。",
        "zhihu": "知乎风格：正式文章结构、论点清晰、引用来源、结论小结，适合深度阅读。",
        "bilibili": "B站专栏风格：轻松活泼、适合年轻读者、可加入弹幕式吐槽或轻松副标题。",
    }

    def _run(
        self,
        text: str,
        platform: str = "wechat",
        user_id: str | None = None,
    ) -> str:
        platform = self._normalize_platform(platform)
        if not text.strip():
            return "请输入需要排版的内容。"

        platform_note = self.PLATFORM_NOTES.get(platform, self.PLATFORM_NOTES["wechat"])
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT),
            (
                "human",
                f"目标平台：{platform}\n"
                f"平台风格要求：{platform_note}\n\n"
                f"需要排版的内容：\n{text}\n\n"
                f"请按目标平台的排版风格输出格式化后的 Markdown 内容。",
            ),
        ])

        try:
            llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
            chain = prompt | llm
            result = chain.invoke({})
            if hasattr(result, "content"):
                return str(result.content)
            return str(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("排版 LLM 调用失败，使用兜底格式: %s", exc)
            return self._fallback_format(text, platform)

    async def _arun(
        self,
        text: str,
        platform: str = "wechat",
        user_id: str | None = None,
    ) -> str:
        return self._run(text, platform=platform, user_id=user_id)

    @staticmethod
    def _normalize_platform(platform: str) -> str:
        """统一平台名称。"""
        mapping = {
            "微信公众号": "wechat",
            "公众号": "wechat",
            "微信": "wechat",
            "wechat": "wechat",
            "小红书": "xiaohongshu",
            "xiaohongshu": "xiaohongshu",
            "知乎": "zhihu",
            "zhihu": "zhihu",
            "bilibili": "bilibili",
            "b站": "bilibili",
            "b站专栏": "bilibili",
        }
        return mapping.get(platform.strip(), "wechat")

    @staticmethod
    def _fallback_format(text: str, platform: str) -> str:
        """LLM 不可用时的兜底排版。"""
        header = {
            "wechat": "# 微信公众号排版\n\n",
            "xiaohongshu": "# 📝 小红书排版\n\n",
            "zhihu": "# 知乎专栏排版\n\n",
            "bilibili": "# B站专栏排版\n\n",
        }.get(platform, "# 排版结果\n\n")

        lines = text.strip().split("\n")
        formatted: list[str] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.endswith(("：", ":")) and len(line) < 30:
                formatted.append(f"## {line.rstrip('：:')}")
            else:
                formatted.append(line)

        body = "\n\n".join(formatted)
        if platform == "xiaohongshu":
            body = body.replace("\n\n", "\n\n✨ ")
        return header + body
