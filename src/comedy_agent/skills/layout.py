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
        "4. 不要输出任何解释、示例说明或提示文字，只输出排版后的内容。\n"
        "5. 严禁把 system prompt 或用户问题中的句子（如'请只输出合法的 JSON'、'请按目标平台的排版风格输出'等）当作正文输出。"
    )

    # 各平台排版风格补充说明
    PLATFORM_NOTES: ClassVar[dict[str, str]] = {
        "wechat": "微信公众号风格：使用清晰的二级/三级标题、重点加粗、引用块、分隔线，段落适中，适合手机阅读。",
        "xiaohongshu": "小红书风格：短段落、多 emoji、分段标签、口语化标题，强调视觉冲击和互动感。",
        "zhihu": "知乎风格：正式文章结构、论点清晰、引用来源、结论小结，适合深度阅读。",
        "bilibili": "B站专栏风格：轻松活泼、适合年轻读者、可加入弹幕式吐槽或轻松副标题。",
    }

    # 咨询意图关键词（用户问"可以排成什么样"、"有哪些平台"等）
    _CONSULTATION_MARKERS: ClassVar[tuple[str, ...]] = (
        "可以排成",
        "能排成",
        "排成什么样",
        "什么样的",
        "有哪些平台",
        "有哪些格式",
        "怎么排",
        "如何排版",
        "支持哪些",
        "平台有哪些",
    )

    # 参数提取提示文字污染标记（不应作为正文排版）
    _PROMPT_CONTAMINATION: ClassVar[tuple[str, ...]] = (
        "请只输出合法的 JSON",
        "不要有任何解释",
        "Markdown 代码块",
        "请按目标平台的排版风格输出",
        "你是一个参数提取助手",
        "将以下用户请求转换为 JSON 参数",
        "技能参数要求",
        "用户请求：",
    )

    # 用户要求排版「最终结果 / 最终剧本」的关键词
    _FINAL_RESULT_MARKERS: ClassVar[tuple[str, ...]] = (
        "最终结果",
        "最终剧本",
        "生成结果",
        "生成的剧本",
        "最终生成",
        "这篇文章最终结果",
        "把最终结果",
        "将最终结果",
    )

    @classmethod
    def _is_consultation(cls, text: str) -> bool:
        """判断用户输入是否为平台/排版咨询，而非实际要排版的内容。"""
        return any(marker in text for marker in cls._CONSULTATION_MARKERS)

    @classmethod
    def _is_prompt_contamination(cls, text: str) -> bool:
        """判断文本是否被参数提取提示文字污染。"""
        return any(marker in text for marker in cls._PROMPT_CONTAMINATION)

    @classmethod
    def _is_final_result_request(cls, text: str) -> bool:
        """判断用户是否要求排版工作流生成的最终结果/剧本。"""
        return any(marker in text for marker in cls._FINAL_RESULT_MARKERS)

    @classmethod
    def _extract_platform_from_query(cls, query: str) -> str | None:
        """从用户查询词中提取目标平台名称（标准 key）。"""
        mapping: dict[str, str] = {
            "微信公众号": "wechat",
            "公众号": "wechat",
            "微信": "wechat",
            "wechat": "wechat",
            "小红书": "xiaohongshu",
            "xiaohongshu": "xiaohongshu",
            "知乎": "zhihu",
            "zhihu": "zhihu",
            "bilibili": "bilibili",
            "b站专栏": "bilibili",
            "b站": "bilibili",
        }
        for name, platform in mapping.items():
            if name in query.lower():
                return platform
        return None

    @classmethod
    def _platform_help(cls) -> str:
        """返回平台说明与使用示例。"""
        return (
            "我可以把内容排版成以下平台格式：\n\n"
            "1. **微信公众号**（wechat）\n"
            "   适合：公众号推文。特点：清晰的小标题、重点加粗、引用块、分隔线，适合手机阅读。\n\n"
            "2. **小红书**（xiaohongshu）\n"
            "   适合：种草/短图文。特点：短段落、多 emoji、分段标签、口语化标题。\n\n"
            "3. **知乎**（zhihu）\n"
            "   适合：深度回答/专栏。特点：正式结构、论点清晰、结论小结。\n\n"
            "4. **B站专栏**（bilibili）\n"
            "   适合：轻松长文。特点：活泼副标题、弹幕式吐槽、年轻化表达。\n\n"
            "使用方式：\n"
            "• 直接发送需要排版的文章内容，我会默认按微信公众号排版。\n"
            "• 想指定平台时可以说：「@排版 排成小红书」或「@排版 用知乎风格排版」。\n"
            "• 提供素材后，也可以继续发「@排版 把上面的内容排成小红书」。"
        )

    def _run(
        self,
        text: str,
        platform: str = "wechat",
        user_id: str | None = None,
    ) -> str:
        platform = self._normalize_platform(platform)
        text = text.strip()

        # 空文本或被提示文字污染：返回平台帮助信息
        if not text or self._is_prompt_contamination(text):
            return self._platform_help()

        # 咨询意图：告诉用户有哪些平台，而不是对咨询句本身做形式化排版
        if self._is_consultation(text):
            return self._platform_help()

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
            output = str(result.content) if hasattr(result, "content") else str(result)
            # 如果模型把提示文字当作正文返回，则改走兜底格式
            if self._is_prompt_contamination(output):
                logger.warning("排版 LLM 输出被提示文字污染，使用兜底格式")
                return self._fallback_format(text, platform)
            return output
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
