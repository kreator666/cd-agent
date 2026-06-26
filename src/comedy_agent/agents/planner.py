"""创作计划 Worker。

根据用户请求和分析结果生成 Todo List 与段落 Outline。
使用普通文本输出 + 稳健解析，兼容返回 markdown/非 JSON 的模型。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.agents.schemas import PlanResult
from comedy_agent.models.factory import ModelFactory
from comedy_agent.state.schema import ComedyState

logger = logging.getLogger(__name__)

PROMPT = """你是一位脱口秀结构规划师。请根据以下分析和用户请求，生成一个创作计划。

用户请求：{user_input}
分析结果：
- 话题：{topic}
- 态度：{attitude}
- 偏见注意：{bias}
- 情绪基调：{emotion}

请严格按以下格式输出：

todo:
1. 第一步任务
2. 第二步任务
3. 第三步任务

outline:
1. 第一段一句话描述
2. 第二段一句话描述
3. 第三段一句话描述
4. 第四段一句话描述（可选）
5. 第五段一句话描述（可选）

tone: 整体语气建议，如“讽刺、自嘲、温暖”

只输出上述格式，不要解释、不要 markdown 代码块。"""

_DEFAULT_RESULT = PlanResult(
    todo=["分析话题", "生成大纲", "逐段写作", "整体审核"],
    outline=[
        "第一段：开场/铺垫，引入话题",
        "第二段：展开观察，建立共鸣",
        "第三段：转折或升级，强化冲突",
        "第四段：收尾/Callback，给出结论",
    ],
    tone="日常观察",
)


class PlannerAgent:
    """创作计划 Agent。"""

    def run(self, state: ComedyState, llm: BaseChatModel | None = None) -> dict[str, Any]:
        """生成创作计划。

        Args:
            state: 当前图状态。
            llm: 可选的外部 LLM。

        Returns:
            包含 ``plan``、``phase``、``current_section``、``sections`` 的更新字典。
        """
        if llm is None:
            llm = ModelFactory.get_model(
                state.model, task_type="analytical"
            )

        analysis = state.analysis or {}
        prompt = PROMPT.format(
            user_input=state.user_input,
            topic=analysis.get("topic", ""),
            attitude=analysis.get("attitude", ""),
            bias=analysis.get("bias", ""),
            emotion=analysis.get("emotion", ""),
        )

        try:
            response = llm.invoke([("human", prompt)])
            content = str(getattr(response, "content", response))
            result = self._parse_content(content)
        except Exception as e:
            logger.warning("计划生成调用失败，使用默认大纲: %s", e)
            result = _DEFAULT_RESULT

        logger.debug("planner: outline=%d", len(result.outline))
        return {
            "plan": result.model_dump(),
            "phase": "plan_review",
            "current_section": 0,
            "sections": [],
        }

    def _parse_content(self, content: str) -> PlanResult:
        """从普通文本中解析 todo / outline / tone。"""
        # 尝试先去掉可能的 markdown 代码块标记
        text = re.sub(r"```(?:json|markdown|text)?\s*", "", content)
        text = text.replace("```", "")

        sections: dict[str, str] = {}
        current_key: str | None = None
        current_lines: list[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            header_match = re.match(r"^(todo|outline|tone)[:：]\s*(.*)$", stripped, re.IGNORECASE)
            if header_match:
                if current_key is not None:
                    sections[current_key] = "\n".join(current_lines)
                current_key = header_match.group(1).lower()
                rest = header_match.group(2).strip()
                current_lines = [rest] if rest else []
            elif current_key is not None and stripped:
                current_lines.append(stripped)

        if current_key is not None:
            sections[current_key] = "\n".join(current_lines)

        todo = self._extract_list_items(sections.get("todo", ""))
        outline = self._extract_list_items(sections.get("outline", ""))
        tone = sections.get("tone", "").strip() or _DEFAULT_RESULT.tone

        if not todo or not outline:
            logger.warning("计划解析结果不完整，使用默认大纲")
            return _DEFAULT_RESULT

        return PlanResult(todo=todo, outline=outline, tone=tone)

    @staticmethod
    def _extract_list_items(text: str) -> list[str]:
        """从编号/ bullet 列表中提取条目。"""
        items: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(?:\d+[.．、]|[-\*•])\s*(.+)$", line)
            if match:
                items.append(match.group(1).strip())
        return items
