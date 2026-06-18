"""喜剧龙虾 Skill —— 专业版角色调度器（V3）。

基于"单引擎 + 动态 System Prompt + 角色接力"理念：
- 不采用多模型路由，而是固定模型实例 + 动态角色提示词切换。
- 根据用户语义自动选择角色、填充槽位、调用工具。
- 每个角色必须 cue 下一个人，不能 cue 自己。
- 输出统一为 JSON，支持聊天区发言、工作台 artifacts、附件 attachments。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from comedy_agent.core.prompt_manager import PromptManager
from comedy_agent.skills.base import ComedySkill

logger = logging.getLogger(__name__)


class GetDarenArgs(BaseModel):
    """喜剧龙虾调度参数。"""

    workflow_step: dict[str, Any] = Field(description="当前工作流状态配置")
    slots: dict[str, Any] = Field(default_factory=dict, description="已收集槽位")
    outputs: dict[str, Any] = Field(default_factory=dict, description="各 Skill 历史输出")
    user_input: str = Field(default="", description="用户最新输入")
    conversation_history: list[dict[str, Any]] = Field(
        default_factory=list, description="最近对话历史"
    )
    user_id: str | None = Field(default=None, description="用户 ID")
    current_role: str | None = Field(default="主持人", description="当前发言角色")
    attachments: list[dict[str, Any]] = Field(default_factory=list, description="角色间附件")
    decision_nodes: list[dict[str, Any]] = Field(default_factory=list, description="决策节点链表")


# ------------------------------------------------------------------ #
# 角色注册表
# ------------------------------------------------------------------ #
CORE_SLOTS: tuple[str, ...] = ("话题", "态度", "偏见", "情绪")

ROLE_REGISTRY: dict[str, dict[str, Any]] = {
    "主持人": {
        "prompt": "pro/host",
        "next_default": "话题专家",
        "can_fill_slot": None,
        "tool": None,
    },
    "话题专家": {
        "prompt": "pro/topic_expert",
        "next_default": "态度专家",
        "can_fill_slot": "话题",
        "tool": None,
    },
    "态度专家": {
        "prompt": "pro/attitude_expert",
        "next_default": "偏见专家",
        "can_fill_slot": "态度",
        "tool": None,
    },
    "偏见专家": {
        "prompt": "pro/bias_expert",
        "next_default": "情绪专家",
        "can_fill_slot": "偏见",
        "tool": None,
    },
    "情绪专家": {
        "prompt": "pro/emotion_expert",
        "next_default": "总编",
        "can_fill_slot": "情绪",
        "tool": None,
    },
    "素材调研员": {
        "prompt": "pro/material_researcher",
        "next_default": "用户",
        "can_fill_slot": None,
        "tool": "material",
    },
    "排版专员": {
        "prompt": "pro/layout_editor",
        "next_default": "用户",
        "can_fill_slot": None,
        "tool": "layout",
    },
    "总编": {
        "prompt": "pro/chief_editor",
        "next_default": "用户",
        "can_fill_slot": None,
        "tool": None,
    },
}

# 中文 mention -> 角色名
MENTION_TO_ROLE: dict[str, str] = {
    "话题": "话题专家",
    "态度": "态度专家",
    "偏见": "偏见专家",
    "情绪": "情绪专家",
    "素材": "素材调研员",
    "排版": "排版专员",
    "总编": "总编",
    "主持人": "主持人",
    "喜剧龙虾": "主持人",
}

# 角色 -> 可填充槽位
ROLE_TO_SLOT: dict[str, str] = {
    "话题专家": "话题",
    "态度专家": "态度",
    "偏见专家": "偏见",
    "情绪专家": "情绪",
}

SLOT_TO_ROLE: dict[str, str] = {v: k for k, v in ROLE_TO_SLOT.items()}


class Skill(ComedySkill):
    """喜剧龙虾 —— 专业版角色调度器（V3）。"""

    name: str = "get_daren"
    description: str = (
        "喜剧龙虾 —— 专业版创作流程的中央调度助手。"
        "基于单引擎+动态角色提示词，负责根据用户语义选择角色、填充槽位、调用工具并聚合最终结果。"
    )
    args_schema: type[BaseModel] = GetDarenArgs
    task_type: str = "analytical"

    CORE_SLOTS: ClassVar[tuple[str, ...]] = CORE_SLOTS

    # 各槽位的详细填写建议
    _SLOT_HINTS: ClassVar[dict[str, str]] = {
        "话题": "描述你想创作的主题场景，比如「实习生被领导刁难的职场故事」或「相亲时的尴尬瞬间」。",
        "态度": "按照公式「态度 = 对某件事的评价 + 伴随的情绪 + 可能的行动倾向」来填写。",
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
        current_role: str | None = "主持人",
        attachments: list[dict[str, Any]] | None = None,
        decision_nodes: list[dict[str, Any]] | None = None,
        **_: Any,
    ) -> str:
        slots = slots or {}
        outputs = outputs or {}
        conversation_history = conversation_history or []
        current_role = current_role or "主持人"
        attachments = attachments or []
        decision_nodes = decision_nodes or []

        # 1. 意图分类：用户想做什么？
        intent = self._classify_intent(user_input, current_role, slots)

        # 2. 确定当前角色
        target_role = self._determine_target_role(intent, current_role, slots)

        # 3. 触发词检测（生成）
        if intent.get("trigger_generate"):
            return self._handle_generate(slots, outputs, user_id, attachments, current_role)

        # 4. 工具调用（素材 / 排版）
        tool_name = ROLE_REGISTRY.get(target_role, {}).get("tool")
        if tool_name and intent.get("want_tool_call"):
            return self._handle_tool_call(
                tool_name, user_input, slots, outputs, user_id, target_role, attachments
            )

        # 5. 槽位自动填充：非提问句式且话题为空时，自动识别为话题
        if not slots.get("话题") and user_input.strip() and not self._is_question(user_input):
            target_role = "话题专家"
            intent = {
                "type": "fill_slot",
                "slot_name": "话题",
                "slot_value": user_input.strip(),
                "mentioned_role": None,
            }

        # 6. 渲染角色提示词并调用 LLM
        context = self._build_context(
            target_role, slots, outputs, attachments, decision_nodes, conversation_history, user_input
        )
        system_prompt = self._render_role_prompt(target_role)
        user_prompt = self._build_user_prompt(context, intent)

        try:
            llm_output = self._call_llm(system_prompt, user_prompt)
            parsed = self._parse_json_output(llm_output)
        except Exception as e:
            logger.error("角色 %s LLM 调用失败: %s", target_role, e, exc_info=True)
            parsed = self._fallback_reply(target_role, intent, slots)

        # 7. 校验与修正 next_role（不能 cue 自己）
        next_role = parsed.get("next_role", "")
        if not next_role or next_role == target_role:
            next_role = ROLE_REGISTRY.get(target_role, {}).get("next_default", "用户")
        parsed["next_role"] = next_role
        parsed["role"] = target_role

        # 8. 处理槽位填充
        slots_update = {}
        if intent.get("type") == "fill_slot" and intent.get("slot_name"):
            slot_name = intent["slot_name"]
            slot_value = intent.get("slot_value", user_input.strip())
            slots_update[slot_name] = slot_value
            parsed["slots_update"] = slots_update

        # 如果 LLM 也返回了 slot 更新，合并
        if parsed.get("slot_name") and parsed.get("slot_value"):
            slots_update[parsed["slot_name"]] = parsed["slot_value"]
            parsed["slots_update"] = slots_update

        # 9. 更新 outputs（工具输出等）
        outputs_update = parsed.get("outputs_update", {})
        if parsed.get("tool_output"):
            outputs_update[parsed.get("tool_name", "tool")] = parsed["tool_output"]
            parsed["outputs_update"] = outputs_update

        # 10. 处理 artifacts（写入 outputs 兼容旧逻辑），长 artifact 同时生成 attachment
        artifacts = parsed.get("artifacts", [])
        new_attachments = list(parsed.get("attachments", []))
        if artifacts:
            # 将 artifact 内容同步到 outputs 中，便于旧版前端读取
            for art in artifacts:
                outputs_update[f"artifact_{art.get('type')}_{art.get('id')}"] = art.get("content", "")
                # 长内容自动生成 attachment，便于下游角色引用
                content = art.get("content", "")
                if len(content) > 500 and not any(a.get("name") == art.get("title") for a in new_attachments):
                    new_attachments.append({
                        "id": f"att_{uuid.uuid4().hex[:6]}",
                        "name": art.get("title") or f"{art.get('type')}_{art.get('id')}",
                        "summary": content[:300] + "..." if len(content) > 300 else content,
                        "full_text": content,
                        "mime_type": "text/plain",
                    })
            parsed["outputs_update"] = outputs_update
            parsed["attachments"] = new_attachments

        # 11. 记录决策节点
        self._record_decision_node(
            decision_nodes,
            node_type="role_switch" if target_role != current_role else "chat",
            role=target_role,
            summary=f"{'切换到' if target_role != current_role else ''}{target_role}: {user_input[:60]}",
            details={
                "intent": intent,
                "slot_filled": list(slots_update.keys()),
                "artifacts": [a.get("id") for a in artifacts],
            },
        )

        # 12. 构造最终返回（兼容旧格式 + 新格式）
        result = {
            "reply": parsed.get("reply", ""),
            "advance": bool(slots_update),
            "slots_update": slots_update,
            "outputs_update": outputs_update,
            "role": target_role,
            "next_role": next_role,
            "artifacts": artifacts,
            "attachments": parsed.get("attachments", []),
            "current_role": target_role,
        }

        return json.dumps(result, ensure_ascii=False)

    # ------------------------------------------------------------------ #
    # 意图分类
    # ------------------------------------------------------------------ #
    def _classify_intent(
        self, user_input: str, current_role: str, slots: dict[str, Any]
    ) -> dict[str, Any]:
        """分析用户意图，决定下一步动作。"""
        text = user_input.strip()
        intent: dict[str, Any] = {"type": "chat", "mentioned_role": None, "slot_name": None}

        # 1. 检测 @mention
        mention = self._detect_mention(text)
        if mention:
            intent["mentioned_role"] = mention
            intent["type"] = "switch_role"
            # 如果是核心槽位 @话题 / @态度 等，同时视为填槽
            if mention in ("话题专家", "态度专家", "偏见专家", "情绪专家"):
                slot = ROLE_TO_SLOT.get(mention)
                if slot:
                    intent["type"] = "fill_slot"
                    intent["slot_name"] = slot
                    intent["slot_value"] = self._extract_mention_content(text, slot)
            return intent

        # 2. 检测生成触发词
        trigger_words = ("生成", "生成剧本", "完成", "done", "finish")
        clean = text.rstrip("。！.!?")
        if clean in trigger_words or any(w in clean for w in trigger_words):
            intent["trigger_generate"] = True
            return intent

        # 3. 语义角色跳转（轻量规则）
        semantic_role = self._infer_role_from_text(text)
        if semantic_role and semantic_role != current_role:
            intent["semantic_role"] = semantic_role
            intent["type"] = "switch_role"
            slot = ROLE_TO_SLOT.get(semantic_role)
            if slot:
                intent["slot_name"] = slot
            return intent

        # 4. 当前角色可填充槽位，且用户输入看起来像填槽内容
        slot = ROLE_TO_SLOT.get(current_role)
        if slot and text and not self._is_question(text) and not slots.get(slot):
            intent["type"] = "fill_slot"
            intent["slot_name"] = slot
            intent["slot_value"] = text
            return intent

        return intent

    @staticmethod
    def _detect_mention(user_input: str) -> str | None:
        """检测 @角色，返回标准角色名。"""
        match = re.search(r"@(\S+)", user_input)
        if not match:
            return None
        mention = match.group(1)
        return MENTION_TO_ROLE.get(mention, mention)

    @staticmethod
    def _extract_mention_content(user_input: str, slot_name: str) -> str:
        """提取 @话题 xxx 中的 xxx。"""
        patterns = [
            rf"@{slot_name}\s*(.+)$",
            rf"@{slot_name}(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, user_input, re.MULTILINE)
            if match:
                return match.group(1).strip()
        # 如果 @的是角色名
        role_name = SLOT_TO_ROLE.get(slot_name, slot_name)
        patterns = [
            rf"@{role_name}\s*(.+)$",
            rf"@{role_name}(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, user_input, re.MULTILINE)
            if match:
                return match.group(1).strip()
        return user_input.strip()

    @staticmethod
    def _infer_role_from_text(text: str) -> str | None:
        """根据用户语义推断要跳转的角色。"""
        lower = text.lower()
        # 素材/调研
        if any(k in lower for k in ("找素材", "搜素材", "查资料", "调研", "搜索", "新闻")):
            return "素材调研员"
        # 排版
        if any(k in lower for k in ("排版", "公众号", "小红书", "知乎", "b站", "格式")):
            return "排版专员"
        # 生成
        if any(k in lower for k in ("生成", "写剧本", "开始写", "出稿")):
            return "总编"
        # 话题
        if any(k in lower for k in ("话题", "主题", "写什么", "关于")) and "态度" not in lower:
            return "话题专家"
        # 态度
        if any(k in lower for k in ("态度", "我觉得", "我认为", "愤怒", "支持", "反对")):
            return "态度专家"
        # 偏见
        if any(k in lower for k in ("偏见", "观点", "看法", "视角", "讽刺")):
            return "偏见专家"
        # 情绪
        if any(k in lower for k in ("情绪", "节奏", "氛围", "感动", "爆笑")):
            return "情绪专家"
        return None

    # ------------------------------------------------------------------ #
    # 角色决策
    # ------------------------------------------------------------------ #
    def _determine_target_role(
        self, intent: dict[str, Any], current_role: str, slots: dict[str, Any]
    ) -> str:
        """确定本次由哪个角色发言。"""
        # 用户明确 @ 或语义跳转
        if intent.get("type") == "switch_role":
            role = intent.get("mentioned_role") or intent.get("semantic_role")
            if role and role in ROLE_REGISTRY:
                return role
        # 填槽时，由对应专家发言
        if intent.get("type") == "fill_slot":
            slot = intent.get("slot_name")
            role = SLOT_TO_ROLE.get(slot)
            if role:
                return role
        # 维持当前角色
        if current_role in ROLE_REGISTRY:
            return current_role
        return "主持人"

    # ------------------------------------------------------------------ #
    # Prompt 渲染
    # ------------------------------------------------------------------ #
    def _render_role_prompt(self, role: str) -> str:
        """加载并渲染角色元提示词。"""
        cfg = ROLE_REGISTRY.get(role, ROLE_REGISTRY["主持人"])
        prompt_name = cfg["prompt"]
        try:
            pm = PromptManager()
            return pm.render(prompt_name)
        except Exception as e:
            logger.warning("加载角色提示词 %s 失败: %s", prompt_name, e)
            return self._default_role_prompt(role)

    @staticmethod
    def _default_role_prompt(role: str) -> str:
        """默认角色提示词（降级）。"""
        return (
            f"你是喜剧创作团队中的「{role}」。"
            "请根据用户输入和当前创作状态，给出专业回应。"
            "必须在结尾 cue 下一个人，不能 cue 自己。"
            "输出必须是 JSON：{\"reply\":\"...\",\"next_role\":\"...\"}"
        )

    def _build_context(
        self,
        role: str,
        slots: dict[str, Any],
        outputs: dict[str, Any],
        attachments: list[dict[str, Any]],
        decision_nodes: list[dict[str, Any]],
        conversation_history: list[dict[str, Any]],
        user_input: str,
    ) -> dict[str, Any]:
        """构建角色提示词上下文变量。"""
        # 最近决策节点摘要
        recent_nodes = decision_nodes[-6:]
        node_summary = "\n".join(
            f"- [{n.get('role')}] {n.get('summary', '')}" for n in recent_nodes
        )

        # 附件摘要
        attachment_summary = ""
        for att in attachments:
            full_text = att.get("full_text", "")
            summary = att.get("summary", "")
            display = summary if summary else (full_text[:300] + "..." if len(full_text) > 300 else full_text)
            attachment_summary += f"\n【附件：{att.get('name', '')}】\n{display}\n"

        # 最近对话
        history_text = "\n".join(
            f"{m.get('role', 'unknown')}: {str(m.get('content', ''))[:200]}"
            for m in conversation_history[-6:]
        )

        return {
            "role": role,
            "slots": slots,
            "outputs": outputs,
            "attachments": attachments,
            "attachment_summary": attachment_summary.strip(),
            "decision_nodes": recent_nodes,
            "node_summary": node_summary,
            "conversation_history": history_text,
            "user_input": user_input,
            "next_default": ROLE_REGISTRY.get(role, {}).get("next_default", "用户"),
            "can_fill_slot": ROLE_REGISTRY.get(role, {}).get("can_fill_slot", ""),
        }

    def _build_user_prompt(self, context: dict[str, Any], intent: dict[str, Any]) -> str:
        """构建给 LLM 的用户 prompt。"""
        parts = [
            f"当前角色：{context['role']}",
            f"用户输入：{context['user_input']}",
            f"已收集槽位：{json.dumps(context['slots'], ensure_ascii=False)}",
            f"用户意图：{intent.get('type')}",
        ]
        if intent.get("slot_name"):
            parts.append(f"待填充槽位：{intent['slot_name']} = {intent.get('slot_value', '')}")
        if context["attachment_summary"]:
            parts.append(f"附件参考：\n{context['attachment_summary']}")
        if context["node_summary"]:
            parts.append(f"最近决策节点：\n{context['node_summary']}")
        if context["conversation_history"]:
            parts.append(f"最近对话：\n{context['conversation_history']}")
        parts.append(f"默认下一个角色：{context['next_default']}")
        parts.append("请按角色提示词要求输出 JSON。")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ #
    # LLM 调用与输出解析
    # ------------------------------------------------------------------ #
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM。"""
        from comedy_agent.models.factory import ModelFactory
        from langchain_core.prompts import ChatPromptTemplate

        messages = [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
        prompt = ChatPromptTemplate.from_messages(messages)
        llm = ModelFactory.get_model_with_fallback(
            name=self.model_name,
            task_type=self.task_type,
        )
        chain = prompt | llm
        result = chain.invoke({})
        return str(result.content) if hasattr(result, "content") else str(result)

    def _parse_json_output(self, raw: str) -> dict[str, Any]:
        """解析 LLM 输出的 JSON。"""
        text = raw.strip()
        # 去除 markdown 代码块
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        # 降级：把整段文本作为 reply
        return {"reply": text}

    def _fallback_reply(self, role: str, intent: dict[str, Any], slots: dict[str, Any]) -> dict[str, Any]:
        """LLM 失败时的降级回复。"""
        next_default = ROLE_REGISTRY.get(role, {}).get("next_default", "用户")
        if intent.get("type") == "fill_slot":
            slot = intent["slot_name"]
            return {
                "reply": f"✅ 已记录{slot}。",
                "next_role": next_default,
                "slot_name": slot,
                "slot_value": intent.get("slot_value", ""),
            }
        return {
            "reply": f"{role}正在处理中，请继续。",
            "next_role": next_default,
        }

    # ------------------------------------------------------------------ #
    # 工具调用
    # ------------------------------------------------------------------ #
    def _handle_tool_call(
        self,
        tool_name: str,
        user_input: str,
        slots: dict[str, Any],
        outputs: dict[str, Any],
        user_id: str | None,
        role: str,
        attachments: list[dict[str, Any]],
    ) -> str:
        """调用外部 Skill（material / layout 等）。"""
        orch = getattr(self, "orchestrator", None)
        if orch is None:
            return json.dumps(
                {"reply": "❌ 编排器未就绪", "next_role": role, "outputs_update": {}},
                ensure_ascii=False,
            )

        skill = orch._find_skill(tool_name)
        if skill is None:
            return json.dumps(
                {"reply": f"❌ 未找到 {tool_name} skill", "next_role": role, "outputs_update": {}},
                ensure_ascii=False,
            )

        # 提取查询词
        user_query = re.sub(r"@\S+", "", user_input).strip("，,。. ")
        topic = slots.get("话题", "")

        try:
            if tool_name == "material":
                output = skill.invoke({"query": user_query or topic, "topic": topic})
                artifact = {
                    "id": f"research_{uuid.uuid4().hex[:6]}",
                    "type": "research",
                    "title": f"关于「{topic or user_query}」的调研报告",
                    "content": str(output),
                    "op": "create",
                    "version": 1,
                    "created_by": "素材调研员",
                }
                # 同时生成 attachment
                summary = str(output)[:300] + "..." if len(str(output)) > 300 else str(output)
                attachment = {
                    "id": f"att_{uuid.uuid4().hex[:6]}",
                    "name": f"素材：{topic or user_query}",
                    "summary": summary,
                    "full_text": str(output),
                    "mime_type": "text/plain",
                }
                return json.dumps(
                    {
                        "reply": f"🔍 已完成关于「{topic or user_query}」的素材调研。",
                        "next_role": "用户",
                        "outputs_update": {tool_name: str(output)},
                        "artifacts": [artifact],
                        "attachments": [attachment],
                    },
                    ensure_ascii=False,
                )
            elif tool_name == "layout":
                content_to_layout = outputs.get("final_script", "") or user_query
                output = skill.invoke({"text": content_to_layout, "platform": "wechat"})
                artifact = {
                    "id": f"layout_{uuid.uuid4().hex[:6]}",
                    "type": "script",
                    "title": "剧本（微信公众号版）",
                    "content": str(output),
                    "op": "create",
                    "version": 1,
                    "created_by": "排版专员",
                }
                return json.dumps(
                    {
                        "reply": "📝 已完成微信公众号排版。",
                        "next_role": "用户",
                        "outputs_update": {tool_name: str(output)},
                        "artifacts": [artifact],
                    },
                    ensure_ascii=False,
                )
            else:
                output = skill.invoke({"text": user_query})
                return json.dumps(
                    {
                        "reply": f"✅ 已调用 {tool_name}。",
                        "next_role": "用户",
                        "outputs_update": {tool_name: str(output)},
                    },
                    ensure_ascii=False,
                )
        except Exception as e:
            logger.error("工具 %s 调用失败: %s", tool_name, e, exc_info=True)
            return json.dumps(
                {"reply": f"❌ {tool_name} 调用失败：{e}", "next_role": role, "outputs_update": {}},
                ensure_ascii=False,
            )

    # ------------------------------------------------------------------ #
    # 生成处理
    # ------------------------------------------------------------------ #
    def _handle_generate(
        self,
        slots: dict[str, Any],
        outputs: dict[str, Any],
        user_id: str | None,
        attachments: list[dict[str, Any]],
        current_role: str,
    ) -> str:
        """处理生成触发词。"""
        missing = [s for s in self.CORE_SLOTS if not slots.get(s)]
        if missing:
            next_role = SLOT_TO_ROLE.get(missing[0], "主持人")
            return json.dumps(
                {
                    "reply": f"⚠️ 还有以下维度未填写：{'、'.join(missing)}。请先补全后再生成。",
                    "next_role": next_role,
                    "slots_update": {},
                    "outputs_update": {},
                },
                ensure_ascii=False,
            )

        # 四维度已齐：询问生成方式
        if outputs.get("final_script"):
            # 已生成过，重新生成
            return self._do_generate(slots, outputs, user_id, attachments, mode="one_shot")

        return json.dumps(
            {
                "reply": "📝 四个维度已集齐。你希望一次性生成完整剧本，还是按小节逐段生成？",
                "next_role": "用户",
                "action": "ask_generate_mode",
                "slots_update": {},
                "outputs_update": {},
            },
            ensure_ascii=False,
        )

    def _do_generate(
        self,
        slots: dict[str, Any],
        outputs: dict[str, Any],
        user_id: str | None,
        attachments: list[dict[str, Any]],
        mode: str = "one_shot",
    ) -> str:
        """调用 standup_generator 生成最终剧本。"""
        context_parts = [f"【{s}】{slots[s]}" for s in self.CORE_SLOTS]

        # 读取相关附件
        for att in attachments:
            full_text = att.get("full_text", "")
            summary = att.get("summary", "")
            display = summary if summary else (full_text[:800] + "..." if len(full_text) > 800 else full_text)
            context_parts.append(f"【{att.get('name', '参考')}】\n{display}")

        topic = "\n\n".join(context_parts)

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
            logger.error("最终生成失败: %s", e, exc_info=True)
            final = f"生成失败：{e}"

        artifact = {
            "id": "script_main",
            "type": "script",
            "title": "最终剧本",
            "content": final,
            "op": "create" if "script_main" not in outputs else "update",
            "version": 1 if "script_main" not in outputs else 2,
            "created_by": "总编",
        }

        return json.dumps(
            {
                "reply": "✅ 剧本已生成，请查看右侧工作台。",
                "next_role": "用户",
                "slots_update": {},
                "outputs_update": {"final_script": final, "script_main": final},
                "artifacts": [artifact],
            },
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------ #
    # 决策节点
    # ------------------------------------------------------------------ #
    @staticmethod
    def _record_decision_node(
        decision_nodes: list[dict[str, Any]],
        node_type: str,
        role: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """记录一个决策节点。"""
        from datetime import datetime, timezone

        decision_nodes.append(
            {
                "node_id": uuid.uuid4().hex[:12],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": node_type,
                "role": role,
                "summary": summary,
                "details": details or {},
            }
        )
        # 只保留最近 30 个节点
        if len(decision_nodes) > 30:
            decision_nodes[:] = decision_nodes[-30:]

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #
    @staticmethod
    def _is_question(user_input: str) -> bool:
        """判断用户输入是否为提问句式。"""
        text = user_input.strip()
        if text.endswith(("?", "？")):
            return True
        question_keywords = (
            "我要做什么", "我该怎么做", "我应该", "怎么", "如何", "什么",
            "为什么", "哪里", "谁", "多少", "吗", "呢", "吧", "能不能",
            "可以吗", "怎么办", "请问", "求助", "帮助",
        )
        lower = text.lower()
        for kw in question_keywords:
            if kw in lower:
                return True
        if re.search(r"[^不没未必](吗|呢|吧)[。！]?$", text):
            return True
        return False
