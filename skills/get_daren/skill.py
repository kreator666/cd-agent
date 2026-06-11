"""Get达人 Skill —— 专业版创作流程中央调度器。"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from comedy_agent.skills.base import ComedySkill


class GetDarenArgs(BaseModel):
    """Get达人调度参数。"""

    workflow_step: dict[str, Any] = Field(description="当前工作流状态配置")
    slots: dict[str, Any] = Field(default_factory=dict, description="已收集槽位")
    outputs: dict[str, Any] = Field(default_factory=dict, description="各 Skill 历史输出")
    user_input: str = Field(default="", description="用户最新输入")
    conversation_history: list[dict[str, Any]] = Field(
        default_factory=list, description="最近对话历史"
    )


class Skill(ComedySkill):
    """Get达人 —— 根据工作流状态执行 collect/select/call/aggregate 动作。"""

    name: str = "get_daren"
    description: str = (
        "Get达人 —— 专业版创作流程的中央调度助手。"
        "负责根据当前工作流状态收集用户输入、引导选择、调用其他 Skill 并聚合提炼最终结果。"
    )
    args_schema: type[BaseModel] = GetDarenArgs
    task_type: str = "analytical"

    def _run(
        self,
        workflow_step: dict[str, Any],
        slots: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        user_input: str = "",
        conversation_history: list[dict[str, Any]] | None = None,
        user_id: str | None = None,
        **_: Any,
    ) -> str:
        slots = slots or {}
        outputs = outputs or {}
        conversation_history = conversation_history or []

        # 1. 检测核心槽位 @mention（话题/态度/偏见/情绪）
        core_slot = self._detect_core_slot(user_input)
        if core_slot:
            slot_name, content = core_slot
            return self._action_fill_slot(slot_name, content, slots)

        # 2. 智能话题识别：非提问句式且话题槽位为空时，自动将输入识别为话题
        if not slots.get("话题") and user_input.strip() and not self._is_question(user_input):
            return self._action_fill_slot("话题", user_input.strip(), slots)

        # 3. 检测"生成"指令
        trigger_words = ("生成", "生成剧本", "完成", "done", "finish")
        clean_input = user_input.strip().rstrip("。！.!?")
        is_trigger = clean_input in trigger_words or any(w in clean_input for w in trigger_words)
        if is_trigger:
            return self._action_trigger_aggregate(slots, outputs, user_id)

        # 4. 根据 workflow_step 执行其他动作
        action = workflow_step.get("action", "guide")
        if action == "collect":
            return self._action_collect(workflow_step, slots, user_input)
        if action == "select":
            return self._action_select(workflow_step, slots, user_input)
        if action == "aggregate":
            return self._action_aggregate(workflow_step, slots, outputs, user_id)
        if action == "guide":
            return self._action_guide(slots, outputs)

        # 默认：guide
        return self._action_guide(slots, outputs)

    # ------------------------------------------------------------------ #
    # collect：收集单个槽位
    # ------------------------------------------------------------------ #
    def _action_collect(
        self,
        step: dict[str, Any],
        slots: dict[str, Any],
        user_input: str,
    ) -> str:
        slot = step.get("slot", "")
        message = step.get("message", "请提供必要信息：")

        # 如果用户输入不为空，收集该槽位
        if user_input.strip():
            val = user_input.strip()
            return json.dumps(
                {
                    "reply": f"✅ 已记录：{val[:60]}{'...' if len(val) > 60 else ''}",
                    "advance": True,
                    "slots_update": {slot: val},
                    "outputs_update": {},
                },
                ensure_ascii=False,
            )

        # 如果槽位已有值，直接推进
        if slots.get(slot):
            return json.dumps(
                {
                    "reply": f"✅ {slot}已确认，继续下一步。",
                    "advance": True,
                    "slots_update": {},
                    "outputs_update": {},
                },
                ensure_ascii=False,
            )

        # 否则追问，追加当前步骤说明
        step_hint = ""
        if slot == "outline":
            step_hint = "\n\n📋 **当前步骤：确定创作主题**\n我需要了解你想写什么内容，才能为你匹配合适的专家团队。"
        reply = f"{message}{step_hint}"
        return json.dumps(
            {
                "reply": reply,
                "advance": False,
                "slots_update": {},
                "outputs_update": {},
            },
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------ #
    # select：引导用户从 skill_type 中选择一项
    # ------------------------------------------------------------------ #
    def _action_select(
        self,
        step: dict[str, Any],
        slots: dict[str, Any],
        user_input: str,
    ) -> str:
        skill_type = step.get("skill_type", "")
        message = step.get("message", "请选择一个选项：")
        slot = step.get("slot") or f"selected_{skill_type}"

        # 步骤说明
        step_desc = {
            "genre": "📋 **当前步骤：选择剧本体裁**\n不同体裁决定了整体创作风格（如脱口秀、相声、小品等），影响后续专家的创作方向。",
            "topic": "📋 **当前步骤：选择话题专家**\n话题专家负责扩写背景、冲突点和场景设定。",
            "attitude": "📋 **当前步骤：选择态度导师**\n态度导师负责为剧本注入核心态度（如讽刺、自嘲、批判等）。",
            "emotion": "📋 **当前步骤：选择情绪设计师**\n情绪设计师负责调整节奏起伏和情感曲线。",
        }.get(skill_type, "")

        # 如果用户已选择过，直接推进
        if slots.get(slot):
            return json.dumps(
                {
                    "reply": f"✅ 已选择 {skill_type}：{slots[slot]}",
                    "advance": True,
                    "slots_update": {},
                    "outputs_update": {},
                },
                ensure_ascii=False,
            )

        # 尝试从用户输入中匹配选择
        selected = ""
        if user_input.strip():
            import re
            mention = re.search(r"@(\S+)", user_input)
            if mention:
                selected = mention.group(1)
            else:
                selected = user_input.strip()

        if selected:
            return json.dumps(
                {
                    "reply": f"✅ 已选择 {skill_type}：{selected}",
                    "advance": True,
                    "slots_update": {slot: selected},
                    "outputs_update": {},
                },
                ensure_ascii=False,
            )

        # 否则列出可选 skill
        options = self._list_skill_options(skill_type)
        options_text = "\n".join([f"• {name} — {desc[:60]}" for name, desc in options])
        reply = f"{message}\n\n{step_desc}\n\n**可选专家：**\n{options_text}\n\n请直接回复选项名称，或 @专家名。"

        return json.dumps(
            {
                "reply": reply,
                "advance": False,
                "slots_update": {},
                "outputs_update": {},
            },
            ensure_ascii=False,
        )

    def _list_skill_options(self, skill_type: str) -> list[tuple[str, str]]:
        """列出指定类型的可用 skills。"""
        orch = getattr(self, "orchestrator", None)
        if orch is None:
            return []
        all_skills = orch.list_skills()
        result = []
        for info in all_skills:
            name = info.get("name", "")
            inferred = self._infer_skill_type(name)
            if inferred == skill_type:
                result.append((name, info.get("description", "")))
        return result

    @staticmethod
    def _infer_skill_type(name: str) -> str:
        if "topic" in name:
            return "topic"
        if "attitude" in name:
            return "attitude"
        if "emotion" in name:
            return "emotion"
        if "genre" in name:
            return "genre"
        if "rule_persona" in name:
            return "rule_persona"
        if "script_composer" in name:
            return "script_composer"
        return "other"

    # ------------------------------------------------------------------ #
    # 核心槽位：话题 / 态度 / 偏见 / 情绪
    # ------------------------------------------------------------------ #
    CORE_SLOTS: ClassVar[tuple[str, ...]] = ("话题", "态度", "偏见", "情绪")

    @classmethod
    def _detect_core_slot(cls, user_input: str) -> tuple[str, str] | None:
        """检测用户输入中的 @话题 / @态度 / @偏见 / @情绪，返回 (槽位名, 内容)。"""
        import re
        for slot_name in cls.CORE_SLOTS:
            pattern = rf"@{slot_name}\s*(.+)$"
            match = re.search(pattern, user_input, re.MULTILINE)
            if match:
                content = match.group(1).strip()
                return slot_name, content
        # 也支持不带空格的变体，如 @话题xxx
        for slot_name in cls.CORE_SLOTS:
            pattern = rf"@{slot_name}(.+)$"
            match = re.search(pattern, user_input, re.MULTILINE)
            if match:
                content = match.group(1).strip()
                if content:
                    return slot_name, content
        return None

    @staticmethod
    def _is_question(user_input: str) -> bool:
        """判断用户输入是否为提问句式。"""
        import re
        text = user_input.strip()
        # 以问号结尾
        if text.endswith(("?", "？")):
            return True
        # 包含典型疑问词
        question_keywords = (
            "我要做什么", "我该怎么做", "我应该", "怎么", "如何", "什么",
            "为什么", "哪里", "谁", "多少", "吗", "呢", "吧", "能不能",
            "可以吗", "怎么办", "请问", "求助", "帮助",
        )
        lower = text.lower()
        for kw in question_keywords:
            if kw in lower:
                return True
        # 包含"吗"、"呢"、"吧"等句末疑问助词（前面没有否定词）
        if re.search(r"[^不没未必](吗|呢|吧)[。！]?$", text):
            return True
        return False

    def _action_fill_slot(self, slot_name: str, content: str, slots: dict[str, Any]) -> str:
        """保存用户输入到核心槽位。"""
        slots[slot_name] = content
        return json.dumps(
            {
                "reply": f"✅ 已记录 {slot_name}：{content[:80]}{'...' if len(content) > 80 else ''}",
                "advance": True,
                "slots_update": {slot_name: content},
                "outputs_update": {},
            },
            ensure_ascii=False,
        )

    def _build_core_checklist(self, slots: dict[str, Any]) -> list[dict[str, Any]]:
        """根据核心槽位构建流程检查清单。"""
        return [
            {"id": "话题", "label": "话题", "done": bool(slots.get("话题")), "optional": False},
            {"id": "态度", "label": "态度", "done": bool(slots.get("态度")), "optional": False},
            {"id": "偏见", "label": "偏见", "done": bool(slots.get("偏见")), "optional": False},
            {"id": "情绪", "label": "情绪", "done": bool(slots.get("情绪")), "optional": False},
            {"id": "aggregate", "label": "生成最终剧本", "done": "final_script" in slots, "optional": False},
        ]

    @staticmethod
    def _format_core_checklist(checklist: list[dict[str, Any]]) -> str:
        """将核心槽位 checklist 格式化为文本。"""
        lines = ["📋 创作流程："]
        for item in checklist:
            mark = "✅" if item["done"] else "⬜"
            lines.append(f"{mark} {item['label']}")
        return "\n".join(lines)

    @classmethod
    def _build_next_hint_from_core_checklist(cls, checklist: list[dict[str, Any]]) -> str:
        """根据核心槽位 checklist 构建下一步提示。"""
        next_item = next(
            (item for item in checklist if not item["done"] and not item.get("optional")),
            None,
        )
        if next_item:
            if next_item["id"] == "aggregate":
                return '👉 所有维度已填写完成！请回复"生成"来生成最终剧本。'
            return f"👉 下一步：请 @{next_item['id']} 输入相关内容。"
        return '👉 所有维度已填写完成！请回复"生成"来生成最终剧本。'

    def _action_guide(self, slots: dict[str, Any], outputs: dict[str, Any]) -> str:
        """生成下一步提示（checklist 由引擎层通过 step.checklist 单独渲染）。"""
        checklist = self._build_core_checklist(slots)
        next_hint = self._build_next_hint_from_core_checklist(checklist)
        return json.dumps(
            {
                "reply": next_hint,
                "advance": False,
                "slots_update": {},
                "outputs_update": {},
            },
            ensure_ascii=False,
        )

    def _action_trigger_aggregate(
        self, slots: dict[str, Any], outputs: dict[str, Any], user_id: str | None
    ) -> str:
        """检查核心槽位是否填满，然后执行聚合生成最终剧本。"""
        required_slots = list(self.CORE_SLOTS)
        missing = [s for s in required_slots if not slots.get(s)]

        if missing:
            missing_text = "、".join(missing)
            reply = (
                f"⚠️ 还有以下维度未填写：{missing_text}\n\n"
                f"请先使用 @{missing[0]} 输入相关内容，再回复\"生成\"。"
            )
            return json.dumps(
                {
                    "reply": reply,
                    "advance": False,
                    "slots_update": {},
                    "outputs_update": {},
                },
                ensure_ascii=False,
            )

        # 所有槽位已填满，执行聚合
        context_parts = []
        for slot_name in required_slots:
            context_parts.append(f"【{slot_name}】\n{slots[slot_name]}")
        context = "\n\n".join(context_parts)

        system_prompt = (
            "你是一位资深喜剧剧本总编。请根据以下四个维度的输入（话题、态度、偏见、情绪），"
            "整合成一份完整、流畅、可直接演出的喜剧剧本。保留各维度的创意亮点，"
            "消除冗余和冲突，确保人物、情节、笑点自然连贯。只输出剧本正文，不要解释。"
        )
        user_prompt = f"请根据以下素材生成最终剧本：\n\n{context}"

        try:
            final = self._call_llm(system_prompt, user_prompt)
        except Exception as e:
            final = f"聚合失败：{e}"

        return json.dumps(
            {
                "reply": final,
                "advance": True,
                "slots_update": {},
                "outputs_update": {"final_script": final},
            },
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------ #
    # aggregate：聚合所有输出并提炼最终结果
    # ------------------------------------------------------------------ #
    def _action_aggregate(
        self,
        step: dict[str, Any],
        slots: dict[str, Any],
        outputs: dict[str, Any],
        user_id: str | None,
    ) -> str:
        """聚合所有输出并提炼最终结果（兼容新4槽位模式）。"""
        # 优先使用新核心槽位（话题/态度/偏见/情绪）
        core_slots_filled = all(slots.get(s) for s in self.CORE_SLOTS)
        if core_slots_filled:
            return self._action_trigger_aggregate(slots, outputs, user_id)

        # 回退到旧模式（outline + genre + outputs）
        message = step.get("message", "正在生成最终剧本...")
        outline = slots.get("outline", "")
        genre = slots.get("selected_genre", "")

        context_parts = [f"【创作大纲】\n{outline}"]
        if genre:
            context_parts.append(f"【选定体裁】\n{genre}")
        for key, val in outputs.items():
            context_parts.append(f"【{key} 专家输出】\n{val}")
        context = "\n\n".join(context_parts)

        system_prompt = (
            "你是一位资深喜剧剧本总编。请根据以下多位专家的输出和原始大纲，"
            "整合成一份完整、流畅、可直接演出的喜剧剧本。保留各位专家的创意亮点，"
            "消除冗余和冲突，确保人物、情节、笑点自然连贯。只输出剧本正文，不要解释。"
        )
        user_prompt = f"请根据以下素材生成最终剧本：\n\n{context}"

        try:
            final = self._call_llm(system_prompt, user_prompt)
        except Exception as e:
            final = f"聚合失败：{e}"

        return json.dumps(
            {
                "reply": final,
                "advance": True,
                "slots_update": {},
                "outputs_update": {"final_script": final},
            },
            ensure_ascii=False,
        )

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM 生成聚合结果。"""
        from comedy_agent.models.factory import ModelFactory

        messages = [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
        try:
            from langchain_core.prompts import ChatPromptTemplate

            prompt = ChatPromptTemplate.from_messages(messages)
            llm = ModelFactory.get_model_with_fallback(
                name=self.model_name,
                task_type=self.task_type,
            )
            chain = prompt | llm
            result = chain.invoke({})
            return str(result.content) if hasattr(result, "content") else str(result)
        except Exception:
            # 回退：直接调用底层模型
            model = ModelFactory.get_model_with_fallback(
                name=self.model_name,
                task_type=self.task_type,
            )
            raw = model.invoke(user_prompt)
            return str(raw.content) if hasattr(raw, "content") else str(raw)
