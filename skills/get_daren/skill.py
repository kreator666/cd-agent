"""Get达人 Skill —— 专业版创作流程中央调度器。"""

from __future__ import annotations

import json
from typing import Any

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
        action = workflow_step.get("action", "collect")

        if action == "collect":
            return self._action_collect(workflow_step, slots, user_input)
        if action == "select":
            return self._action_select(workflow_step, slots, user_input)
        if action == "call":
            return self._action_call(workflow_step, slots, outputs, user_input, user_id)
        if action == "aggregate":
            return self._action_aggregate(workflow_step, slots, outputs, user_id)

        return json.dumps(
            {
                "reply": f"未知动作类型：{action}",
                "advance": True,
                "slots_update": {},
                "outputs_update": {},
            },
            ensure_ascii=False,
        )

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
            return json.dumps(
                {
                    "reply": f"✅ 已记录：{user_input.strip()[:60]}{'...' if len(user_input.strip()) > 60 else ''}",
                    "advance": True,
                    "slots_update": {slot: user_input.strip()},
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

        # 否则追问
        return json.dumps(
            {
                "reply": message,
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
            # 支持 @name 或直接名称
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
        options_text = "\n".join([f"• {name} — {desc[:40]}" for name, desc in options])
        reply = f"{message}\n\n{options_text}\n\n请直接回复选项名称，或 @专家名。"

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
    # call：调用指定 skill
    # ------------------------------------------------------------------ #
    def _action_call(
        self,
        step: dict[str, Any],
        slots: dict[str, Any],
        outputs: dict[str, Any],
        user_input: str,
        user_id: str | None,
    ) -> str:
        skill_name = step.get("skill", "")
        message = step.get("message", f"正在调用 {skill_name}...")

        orch = getattr(self, "orchestrator", None)
        if orch is None:
            return json.dumps(
                {
                    "reply": f"❌ 编排器未就绪，无法调用 {skill_name}",
                    "advance": True,
                    "slots_update": {},
                    "outputs_update": {},
                },
                ensure_ascii=False,
            )

        # 构建 prompt，优先使用当前文本（上一步输出或大纲）
        current_text = outputs.get("outline") or slots.get("outline", "")
        for key in ["topic", "attitude", "emotion"]:
            if key in outputs:
                current_text = outputs[key]

        if skill_name == "rule_persona":
            persona_id = slots.get("persona_id", "")
            memory = getattr(self, "memory", None)
            rule_content = ""
            if memory and persona_id:
                persona = memory.load_persona(persona_id)
                rule_content = getattr(persona, "rule_content", {}) if persona else {}
            prompt = (
                f"使用 rule_persona 技能。\n"
                f"大纲：{current_text}\n"
                f"规则：{rule_content}"
            )
        elif skill_name == "script_composer":
            context_parts = [f"大纲：{slots.get('outline', '')}"]
            for key, val in outputs.items():
                if key != "outline":
                    context_parts.append(f"【{key} 输出】\n{val}")
            context_text = "\n\n".join(context_parts)
            prompt = f"使用 script_composer 技能。\n上下文：\n{context_text}"
        else:
            prompt = f"使用 {skill_name} 技能。\n文本：{current_text}"

        try:
            result = orch.run(prompt, user_id=user_id)
            output = result.get("output", "")
        except Exception as e:
            return json.dumps(
                {
                    "reply": f"❌ {skill_name} 调用失败：{e}",
                    "advance": False,
                    "slots_update": {},
                    "outputs_update": {},
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "reply": message,
                "advance": True,
                "slots_update": {},
                "outputs_update": {skill_name: output},
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
        message = step.get("message", "正在生成最终剧本...")
        outline = slots.get("outline", "")
        genre = slots.get("selected_genre", "")

        context_parts = [f"【创作大纲】\n{outline}"]
        if genre:
            context_parts.append(f"【选定体裁】\n{genre}")
        for key, val in outputs.items():
            context_parts.append(f"【{key} 专家输出】\n{val}")
        context = "\n\n".join(context_parts)

        # 使用基类内置 LLM 能力生成聚合结果
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
