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

    # 核心工作流程维度（由 Get达人内部处理，不直接调用外部 Skill）
    CORE_SLOTS: ClassVar[tuple[str, ...]] = ("话题", "态度", "偏见", "情绪")

    # 各槽位的详细填写建议
    _SLOT_HINTS: ClassVar[dict[str, str]] = {
        "话题": "描述你想创作的主题场景，比如「实习生被领导刁难的职场故事」或「相亲时的尴尬瞬间」。",
        "态度": "按照公式「态度 = 对某件事的评价 + 伴随的情绪 + 可能的行动倾向」来填写，比如「对加班文化的荒谬感到愤怒，但表面上还要假装积极」。",
        "偏见": "给出一个独特视角或偏见，比如「领导永远是对的」或「加班就是努力」。",
        "情绪": "描述情感节奏变化，比如「从愤怒到释然」或「从紧张到爆笑」。",
    }

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
            return self._action_fill_slot(slot_name, content, slots, user_input)

        # 2. 智能话题识别：非提问句式且话题槽位为空时，自动将输入识别为话题
        if not slots.get("话题") and user_input.strip() and not self._is_question(user_input):
            return self._action_fill_slot("话题", user_input.strip(), slots, user_input)

        # 3. 检测"生成"指令
        trigger_words = ("生成", "生成剧本", "完成", "done", "finish")
        clean_input = user_input.strip().rstrip("。！.!?")
        is_trigger = clean_input in trigger_words or any(w in clean_input for w in trigger_words)
        if is_trigger:
            return self._action_trigger_aggregate(slots, outputs, user_id, user_input)

        # 4. 根据 workflow_step 执行其他动作
        action = workflow_step.get("action", "guide")
        if action == "collect":
            return self._action_collect(workflow_step, slots, user_input)
        if action == "select":
            return self._action_select(workflow_step, slots, user_input)
        if action == "aggregate":
            return self._action_aggregate(workflow_step, slots, outputs, user_id)
        if action == "guide":
            return self._action_guide(slots, outputs, user_input)

        # 默认：guide
        return self._action_guide(slots, outputs, user_input)

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

    # ------------------------------------------------------------------ #
    # 结构化回复构建
    # ------------------------------------------------------------------ #
    def _action_fill_slot(self, slot_name: str, content: str, slots: dict[str, Any], user_input: str = "") -> str:
        """保存用户输入到核心槽位，返回结构化回复（反馈 + 流程列表 + 确认 + 下一步 + 详细建议）。"""
        slots[slot_name] = content
        feedback = self._generate_feedback(slot_name, content, slots, user_input)
        structured = self._build_structured_reply(slots, confirm_slot=slot_name, confirm_content=content)
        reply = f"{feedback}\n\n{structured}"
        return json.dumps(
            {
                "reply": reply,
                "advance": True,
                "slots_update": {slot_name: content},
                "outputs_update": {},
            },
            ensure_ascii=False,
        )

    def _action_guide(self, slots: dict[str, Any], outputs: dict[str, Any], user_input: str = "") -> str:
        """生成结构化回复。有用户输入时先反馈，再给出流程指引。"""
        if user_input.strip():
            feedback = self._generate_feedback(None, None, slots, user_input)
            structured = self._build_structured_reply(slots)
            reply = f"{feedback}\n\n{structured}"
        else:
            reply = self._build_structured_reply(slots)
        return json.dumps(
            {
                "reply": reply,
                "advance": False,
                "slots_update": {},
                "outputs_update": {},
            },
            ensure_ascii=False,
        )

    def _action_trigger_aggregate(
        self, slots: dict[str, Any], outputs: dict[str, Any], user_id: str | None, user_input: str = ""
    ) -> str:
        """检查核心槽位是否填满，然后执行聚合生成最终剧本。"""
        required_slots = list(self.CORE_SLOTS)
        missing = [s for s in required_slots if not slots.get(s)]

        if missing:
            missing_text = "、".join(missing)
            feedback = self._generate_feedback(None, None, slots, user_input)
            checklist = self._build_core_checklist(slots)
            checklist_text = self._format_core_checklist(checklist)
            next_hint = self._build_next_hint_from_core_checklist(checklist)
            detailed_hint = self._build_detailed_hint(checklist, slots)
            structured = (
                f"📋 创作流程：\n{checklist_text}\n\n"
                f"{next_hint}\n\n"
                f"{detailed_hint}"
            )
            reply = (
                f"{feedback}\n\n"
                f"⚠️ 还有以下维度未填写：{missing_text}\n\n"
                f"{structured}"
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

        # 所有槽位已填满，调用 standup skill 生成最终剧本
        context_parts = []
        for slot_name in required_slots:
            context_parts.append(f"【{slot_name}】{slots[slot_name]}")
        topic = " | ".join(context_parts)

        final = ""
        try:
            orch = getattr(self, "orchestrator", None)
            if orch is not None:
                standup_skill = orch._find_skill("standup_generator")
                if standup_skill is not None:
                    final = standup_skill._run(
                        topic=topic,
                        style="日常观察",
                        duration=3,
                        audience="通用",
                        density="标准",
                        perspective_count=2,
                        user_id=user_id,
                        debug=False,
                    )
                else:
                    final = "❌ 未找到 standup_generator skill，请检查 Skill 注册状态。"
            else:
                final = "❌ 编排器未就绪，无法调用外部 Skill。"
        except Exception as e:
            # 回退：使用 LLM 直接聚合
            system_prompt = (
                "你是一位资深喜剧剧本总编。请根据以下四个维度的输入（话题、态度、偏见、情绪），"
                "整合成一份完整、流畅、可直接演出的喜剧剧本。保留各维度的创意亮点，"
                "消除冗余和冲突，确保人物、情节、笑点自然连贯。只输出剧本正文，不要解释。"
            )
            user_prompt = f"请根据以下素材生成最终剧本：\n\n{topic.replace(' | ', chr(10))}"
            try:
                final = self._call_llm(system_prompt, user_prompt)
            except Exception as inner_e:
                final = f"聚合失败：{e}（回退也失败：{inner_e}）"

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
    # 反馈生成：根据用户输入和当前状态生成自然回复
    # ------------------------------------------------------------------ #
    def _generate_feedback(
        self,
        slot_name: str | None,
        content: str | None,
        slots: dict[str, Any],
        user_input: str,
    ) -> str:
        """根据用户输入生成反馈。slot_name 为 None 表示用户没有按流程输入。"""
        if slot_name and content:
            # 用户按流程填充了槽位
            feedbacks = {
                "话题": [
                    f"「{content[:30]}」这个选题很有意思，期待你的创作！",
                    f"好的，以「{content[:30]}」为主题展开，这是个不错的切入点。",
                    f"收到！「{content[:30]}」这个话题很有发挥空间。",
                ],
                "态度": [
                    f"「{content[:30]}」的态度定位很清晰，会让剧本更有棱角。",
                    f"确定了「{content[:30]}」的基调，接下来可以继续深化。",
                    f"态度定为「{content[:30]}」，这会让作品更有辨识度。",
                ],
                "偏见": [
                    f"「{content[:30]}」这个视角很独特，会是很好的笑点来源。",
                    f"独特的偏见视角「{content[:30]}」，这会让剧本更有记忆点。",
                    f"这个偏见设定「{content[:30]}」很有意思，期待成品！",
                ],
                "情绪": [
                    f"「{content[:30]}」的情感节奏设计会让剧本更有张力。",
                    f"情绪线定为「{content[:30]}」，观众会跟着你的节奏走。",
                    f"收到！「{content[:30]}」的情绪变化会让作品更有层次。",
                ],
            }
            import random
            return random.choice(feedbacks.get(slot_name, [f"已记录{slot_name}。"]))

        # 用户没有按流程输入（闲聊、提问、跑题等）
        if not user_input.strip():
            return ""

        # 使用 LLM 先回答用户的问题/闲聊，再衔接回创作流程
        system_prompt = (
            "你是一位专业的喜剧创作助手，名叫 Get达人。"
            "用户正在和你一起进行喜剧剧本创作（流程：话题→态度→偏见→情绪→生成剧本）。"
            "但用户最近的输入没有按流程来，而是在闲聊、提问或跑题。"
            "请先用简短自然的方式回应用户的输入（真正回答他的问题或接住他的话），"
            "然后再温和地提醒他回到创作流程。"
            "控制在 100 字以内。"
        )
        try:
            feedback = self._call_llm(system_prompt, user_input.strip())
            feedback = feedback.strip().replace("\n", " ").strip()
            if len(feedback) > 150:
                feedback = feedback[:147] + "..."
            return feedback
        except Exception:
            # LLM 调用失败时回退到固定模板
            text = user_input.strip()
            if self._is_question(text):
                return (
                    "这个问题问得好！不过我们现在正在创作剧本，"
                    "建议你按照下面的流程来填写各个维度，完成后就能生成完整的剧本了。"
                )
            if any(kw in text for kw in ("你好", "嗨", "Hello", "hi")):
                return "你好！我是 Get达人，很高兴协助你创作剧本。让我们开始吧！"
            if any(kw in text for kw in ("谢谢", "感谢", "多谢")):
                return "不客气！继续加油，我们离完成剧本越来越近了。"
            if any(kw in text for kw in ("太难了", "不会", "不知道", "迷茫")):
                return (
                    "别担心，创作确实有挑战。你可以参考下面的建议来填写每个维度，"
                    "一步一步来，很快就能完成。"
                )
            return (
                "明白了。如果你想继续创作剧本，可以按照下面的流程来填写各个维度。"
                "每完成一个维度，我们离最终剧本就更近一步！"
            )

    def _build_structured_reply(
        self,
        slots: dict[str, Any],
        confirm_slot: str | None = None,
        confirm_content: str | None = None,
    ) -> str:
        """构建结构层：流程列表 + 确认 + 下一步 + 详细建议。"""
        checklist = self._build_core_checklist(slots)
        checklist_text = self._format_core_checklist(checklist)
        next_hint = self._build_next_hint_from_core_checklist(checklist)
        detailed_hint = self._build_detailed_hint(checklist, slots)

        parts = [f"📋 创作流程：\n{checklist_text}"]
        if confirm_slot and confirm_content:
            parts.append(f"✅ 已确认：{confirm_slot} = {confirm_content[:60]}{'...' if len(confirm_content) > 60 else ''}")
        parts.append(next_hint)
        parts.append(detailed_hint)

        return "\n\n".join(parts)

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
        lines = []
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
                return '👉 下一步：所有维度已填写完成！请回复"生成"来生成最终剧本。'
            return f"👉 下一步：请 @{next_item['id']} 输入相关内容。"
        return '👉 下一步：所有维度已填写完成！请回复"生成"来生成最终剧本。'

    def _build_detailed_hint(self, checklist: list[dict[str, Any]], slots: dict[str, Any]) -> str:
        """根据话题内容和当前缺失槽位生成填写建议：固定话术 + LLM 动态推理。"""
        topic = slots.get("话题", "")
        next_item = next(
            (item for item in checklist if not item["done"] and not item.get("optional")),
            None,
        )
        next_slot = next_item["id"] if next_item else ""

        # 如果话题为空或下一步是生成剧本，回退到固定提示
        if not topic or next_slot in ("", "aggregate"):
            if next_slot in self._SLOT_HINTS:
                return f"💡 建议：{self._SLOT_HINTS[next_slot]}"
            return "💡 建议：继续按流程填写，完成后即可生成最终剧本。"

        # 固定话术映射
        fixed_hints = {
            "态度": "你的态度是支持/反对？喜欢/讨厌？大声的说出来，朋友！",
            "偏见": "说出你对这个话题的观点/洞察，但最好是偏见。理不歪笑不来",
        }
        fixed = fixed_hints.get(next_slot, "")

        # 构建 LLM prompt
        if next_slot == "偏见":
            system_prompt = (
                "你是一位资深喜剧创作顾问。请根据用户提供的创作话题，"
                "给出针对「偏见」维度的简短填写建议。"
                "规则：说出你对这个话题的观点/洞察，但最好是偏见。理不歪笑不来。"
                "建议要有创意、贴合话题、能激发用户灵感，控制在 60 字以内。"
                "只输出建议内容，不要加标题或解释。"
            )
            user_prompt = f"创作话题：{topic}\n请围绕这个话题，按照「理不歪笑不来」的原则，给出填写「偏见」的创意建议。"
        else:
            system_prompt = (
                "你是一位资深喜剧创作顾问。请根据用户提供的创作话题，"
                "给出针对下一个维度的简短填写建议。建议要有创意、贴合话题、能激发用户灵感，"
                "控制在 60 字以内。只输出建议内容，不要加标题或解释。"
            )
            user_prompt = (
                f"创作话题：{topic}\n"
                f"下一步需要填写的维度：{next_slot}\n"
                f"请围绕这个话题，给出填写「{next_slot}」的创意建议。"
            )

        try:
            hint = self._call_llm(system_prompt, user_prompt)
            hint = hint.strip().replace("\n", " ").strip()
            if len(hint) > 120:
                hint = hint[:117] + "..."
            if fixed:
                return f"💡 建议：{fixed}\n💡 {hint}"
            return f"💡 建议：{hint}"
        except Exception:
            # LLM 调用失败时回退
            if fixed:
                return f"💡 建议：{fixed}"
            return f"💡 建议：{self._SLOT_HINTS.get(next_slot, '继续按流程填写，完成后即可生成最终剧本。')}"

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
            return self._action_trigger_aggregate(slots, outputs, user_id, "")

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
