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

# 槽位中文名 -> 状态机状态 ID
SLOT_TO_STATE: dict[str, str] = {
    "话题": "topic_filling",
    "态度": "attitude_filling",
    "偏见": "bias_filling",
    "情绪": "emotion_filling",
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
        current_role = workflow_step.get("role", current_role or "主持人")
        attachments = attachments or []
        decision_nodes = decision_nodes or []

        action = workflow_step.get("action", "guide")
        current_state = workflow_step.get("state_id", "guiding")

        # 0. 选项引用消解：如果用户回复的是选项编号，从上下文中解析出实际内容
        resolved_input = self._resolve_option_reference(user_input, conversation_history)
        if resolved_input:
            logger.debug("选项引用消解：%r -> %r", user_input, resolved_input)
            user_input = resolved_input

        # 1. 意图分类：用户想做什么？
        intent = self._classify_intent(user_input, current_role, slots)

        # 2. 状态机特殊分支
        if action == "ask":
            # 询问生成模式，识别后直接生成，不再只给确认语
            return self._handle_ask_generate_mode(
                user_input, current_state, slots, outputs, user_id, attachments
            )

        if action == "generate":
            # 生成剧本
            mode = workflow_step.get("mode", "one_shot")
            if mode == "section":
                return self._handle_generate_section(slots, outputs, user_id, attachments, user_input, current_state)
            return self._handle_generate_one_shot(slots, outputs, user_id, attachments, current_state)

        if action == "done":
            # 已完成，处理后续指令（修改/排版/保存）
            return self._handle_done_state(user_input, slots, outputs, user_id, attachments, current_role)

        # 3. 触发词检测（生成）
        if intent.get("trigger_generate"):
            return self._handle_generate(slots, outputs, user_id, attachments, current_role, current_state)

        # 4. 确定当前角色
        target_role = self._determine_target_role(intent, current_role, slots)

        # 5. 工具调用（素材 / 排版）
        tool_name = ROLE_REGISTRY.get(target_role, {}).get("tool")
        if tool_name and intent.get("want_tool_call"):
            return self._handle_tool_call(
                tool_name, user_input, slots, outputs, user_id, target_role, attachments
            )

        # 6. 槽位自动填充：非提问句式且话题为空时，自动识别为话题
        if not slots.get("话题") and user_input.strip() and not self._is_question(user_input):
            target_role = "话题专家"
            intent = {
                "type": "fill_slot",
                "slot_name": "话题",
                "slot_value": user_input.strip(),
                "mentioned_role": None,
            }

        # 7. 渲染角色提示词并调用 LLM
        user_confirmed = self._detect_confirmation(user_input)
        context = self._build_context(
            target_role, slots, outputs, attachments, decision_nodes, conversation_history, user_input, user_confirmed
        )
        system_prompt = self._render_role_prompt(target_role)
        user_prompt = self._build_user_prompt(context, intent)

        try:
            llm_output = self._call_llm(system_prompt, user_prompt)
            parsed = self._parse_json_output(llm_output)
        except Exception as e:
            logger.error("角色 %s LLM 调用失败: %s", target_role, e, exc_info=True)
            parsed = self._fallback_reply(target_role, intent, slots)

        # 8. 校验与修正 next_role（不能 cue 自己）
        next_role = parsed.get("next_role", "")
        if not next_role or next_role == target_role:
            next_role = ROLE_REGISTRY.get(target_role, {}).get("next_default", "用户")
        parsed["next_role"] = next_role
        parsed["role"] = target_role

        # 9. 处理槽位填充
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

        # 10. 计算下一状态（只有明确 advance、显式切换角色或用户确认推进时才推进）
        advance = bool(parsed.get("advance", False) or intent.get("type") == "switch_role")
        if user_confirmed and target_role in ROLE_TO_SLOT:
            slot = ROLE_TO_SLOT[target_role]
            if slots.get(slot) or slots_update.get(slot):
                advance = True
        state_update = self._compute_next_state(current_state, slots_update, slots, intent, advance)

        # 11. 更新 outputs（工具输出等）
        outputs_update = parsed.get("outputs_update", {})
        if parsed.get("tool_output"):
            outputs_update[parsed.get("tool_name", "tool")] = parsed["tool_output"]
            parsed["outputs_update"] = outputs_update

        # 12. 处理 artifacts（写入 outputs 兼容旧逻辑），长 artifact 同时生成 attachment
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

        # 13. 记录决策节点
        self._record_decision_node(
            decision_nodes,
            node_type="role_switch" if target_role != current_role else "chat",
            role=target_role,
            summary=f"{'切换到' if target_role != current_role else ''}{target_role}: {user_input[:60]}",
            details={
                "intent": intent,
                "slot_filled": list(slots_update.keys()),
                "artifacts": [a.get("id") for a in artifacts],
                "state_update": state_update,
            },
        )

        # 14. 构造最终返回（兼容旧格式 + 新格式）
        result = {
            "reply": parsed.get("reply", ""),
            "advance": advance,
            "slots_update": slots_update,
            "outputs_update": outputs_update,
            "role": target_role,
            "next_role": next_role,
            "artifacts": artifacts,
            "attachments": parsed.get("attachments", []),
            "current_role": target_role,
            "state_update": state_update,
        }

        return json.dumps(result, ensure_ascii=False)

    def _compute_next_state(
        self,
        current_state: str,
        slots_update: dict[str, Any],
        slots: dict[str, Any],
        intent: dict[str, Any],
        advance: bool = False,
    ) -> dict[str, Any]:
        """根据当前状态和槽位变化计算下一状态。

        只有当前角色明确给出 advance 信号（或用户显式切换角色）时才推进状态，
        否则保持当前状态，支持多轮交互。
        """
        # 显式角色切换：@mention 或语义跳转
        if intent.get("mentioned_role") or intent.get("semantic_role"):
            if advance:
                role = intent.get("mentioned_role") or intent.get("semantic_role")
                slot = ROLE_TO_SLOT.get(role)
                return {"current_state": SLOT_TO_STATE.get(slot, "guiding")}
            return {"current_state": current_state}

        # 未收到 advance 信号时保持当前状态
        if not advance:
            return {"current_state": current_state}

        # collect 动作填完槽位后按顺序推进
        if current_state == "topic_filling" and slots_update.get("话题"):
            return {"current_state": "attitude_filling"}
        if current_state == "attitude_filling" and slots_update.get("态度"):
            return {"current_state": "bias_filling"}
        if current_state == "bias_filling" and slots_update.get("偏见"):
            return {"current_state": "emotion_filling"}
        if current_state == "emotion_filling" and slots_update.get("情绪"):
            return {"current_state": "ask_generate_mode"}

        # 在 guiding 状态下，如果某个槽位被填充，自动推进到下一个未填充槽位
        if current_state == "guiding" and slots_update:
            filled_slot = next(iter(slots_update.keys()))
            slot_order = list(self.CORE_SLOTS)
            idx = slot_order.index(filled_slot) if filled_slot in slot_order else -1
            if idx >= 0 and idx + 1 < len(slot_order):
                next_slot = slot_order[idx + 1]
                if not slots.get(next_slot):
                    return {"current_state": SLOT_TO_STATE.get(next_slot, "guiding")}
            # 所有槽位已填满
            if all(slots.get(s) for s in self.CORE_SLOTS):
                return {"current_state": "ask_generate_mode"}

        # 默认保持当前状态
        return {"current_state": current_state}

    # ------------------------------------------------------------------ #
    # 选项引用消解
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_last_assistant_reply(conversation_history: list[dict[str, Any]]) -> str:
        """从对话历史中提取最后一条助手回复的纯文本内容。

        兼容两种格式：
        - 标准消息格式：{"role": "ai", "content": "..."}
        - 工作流日志格式：{"output": "...", "input": "..."}
        """
        if not conversation_history:
            return ""

        # 优先尝试日志格式：最后一条日志的 output 字段
        last_entry = conversation_history[-1]
        if isinstance(last_entry, dict) and "output" in last_entry:
            return str(last_entry.get("output", ""))

        # 标准消息格式
        for message in reversed(conversation_history):
            role = message.get("role", "").lower()
            if role in ("assistant", "agent", "ai", "model"):
                content = message.get("content", "")
                if isinstance(content, str):
                    return content
                if isinstance(content, dict):
                    return content.get("reply", "") or content.get("text", "") or str(content)
        return ""

    @staticmethod
    def _clean_option_tail(text: str) -> str:
        """清理选项内容末尾的引导语、连接词和标点。"""
        # 去掉常见的列表后引导语
        tail_patterns = [
            r"[。！?？；;，,、]\s*(?:您更倾向|你更倾向|请选择|您想|你想|哪个|怎么选|如何选|哪一个|何者|您选择|你选择).*$",
            r"[。！?？；;，,、]\s*(?:或者|或|还是|and|or)\s*[A-D\d①-⑩].*$",
            r"\s*(?:或者|或|还是|and|or)\s*$",
            r"[。！?？；;，,、]\s*$",
        ]
        for _ in range(3):  # 多次清理，处理嵌套情况
            for pattern in tail_patterns:
                text = re.sub(pattern, "", text, flags=re.DOTALL)
        return text.strip()

    @staticmethod
    def _parse_options(text: str) -> dict[str, str]:
        """从文本中解析有序选项，返回 {label: option_text}。

        支持行内选项，例如：
        - "A) xxx 或 B) yyy。您更倾向哪种？"
        - "1) 职场 2) 校园"
        """
        options: dict[str, str] = {}
        if not text:
            return options

        # 选项标记正则与标签提取器
        marker_patterns: list[tuple[str, Any]] = [
            # 字母 A) / A. / (A)
            (r"[(（]?([a-dA-D])[)）\.．、]", lambda m: m.group(1).lower()),
            # 数字 1) / 1. / (1)
            (r"[(（]?(\d+)[)）\.．、]", lambda m: m.group(1)),
            # 圆圈数字 ①
            (r"([①②③④⑤⑥⑦⑧⑨⑩])", lambda m: m.group(1)),
        ]

        markers: list[tuple[int, int, str]] = []
        for pattern, label_fn in marker_patterns:
            for m in re.finditer(pattern, text):
                markers.append((m.start(), m.end(), label_fn(m)))

        # 中文数字
        cn_pattern = r"(第\s*[一二三四五]\s*[个位]|[一二三四五]、)"
        cn_map = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5"}
        for m in re.finditer(cn_pattern, text):
            label = m.group(1)
            markers.append((m.start(), m.end(), label, cn_map))

        if not markers:
            return options

        # 按位置排序，去重（同一位置保留第一个出现的标签）
        markers.sort(key=lambda x: x[0])
        seen: set[int] = set()
        unique_markers = []
        for marker in markers:
            if marker[0] not in seen:
                unique_markers.append(marker)
                seen.add(marker[0])
        markers = unique_markers

        # 提取每个选项的内容：从当前标记结束到下一个标记开始
        for i, marker in enumerate(markers):
            start, end, label, *extra = marker
            next_start = markers[i + 1][0] if i + 1 < len(markers) else len(text)
            content = text[end:next_start].strip()
            content = Skill._clean_option_tail(content)
            if not content:
                continue
            options[label] = content
            # 字母同时存大小写
            if label.isalpha():
                options[label.upper()] = content
            # 中文数字同时存阿拉伯数字
            if extra:
                cn_map_ref = extra[0]
                for ch, num in cn_map_ref.items():
                    if ch in label:
                        options[num] = content
                        break

        return options

    @staticmethod
    def _parse_option_selector(text: str) -> str | None:
        """判断用户输入是否在选择某个选项，返回标准化标签或 None。"""
        text = text.strip()
        if not text:
            return None

        # 纯数字/字母，如 "1", "a", "A"
        if re.match(r"^\d+$", text):
            return text
        if re.match(r"^[a-dA-D]$", text):
            return text.lower()

        # 选项1 / 选A / 第一个 / 第一 / ①
        patterns = [
            (r"^(?:选|选择|选项)?\s*([a-dA-D])\s*$", True),
            (r"^(?:选|选择|选项)?\s*(\d+)\s*$", False),
            (r"^第\s*([一二三四五])\s*(?:个|位)?$", False),
            (r"^([一二三四五])$", False),
            (r"^([①②③④⑤⑥⑦⑧⑨⑩])$", False),
        ]
        for pattern, lower in patterns:
            m = re.match(pattern, text)
            if m:
                value = m.group(1)
                return value.lower() if lower else value

        return None

    def _resolve_option_reference(
        self,
        user_input: str,
        conversation_history: list[dict[str, Any]],
    ) -> str | None:
        """如果用户回复的是选项编号，从上次助手回复中解析出对应选项内容。"""
        selector = self._parse_option_selector(user_input)
        if not selector:
            return None

        last_reply = self._extract_last_assistant_reply(conversation_history)
        if not last_reply:
            return None

        options = self._parse_options(last_reply)
        if not options:
            return None

        # 中文数字映射
        cn_map = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5"}
        selector = cn_map.get(selector, selector)

        return options.get(selector)

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

        # 注：不再根据当前角色自动把用户输入填槽，避免多轮讨论时把用户的每一句回答都当成槽位值。
        # 槽位填写交给 LLM 自行判断，通过 JSON 中的 slot_name / slot_value 显式返回。
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
            base = pm.render(prompt_name)
        except Exception as e:
            logger.warning("加载角色提示词 %s 失败: %s", prompt_name, e)
            base = self._default_role_prompt(role)

        # 为核心维度专家动态注入「不急于交接」规则，覆盖 prompt 文件中的旧示例
        if role in ROLE_TO_SLOT:
            runtime_rule = (
                "【重要：当前阶段交互规则】\n"
                "你是核心维度专家，请先跟用户多轮讨论、给建议、提问，帮助用户完善素材，"
                "不要收到一条输入就立刻填槽并 cue 下一个人。\n"
                "只有当该维度已经足够完整、用户确认后，才在 JSON 中设置 \"advance\": true "
                "并在 reply 结尾 cue 下一位专家；否则保持 \"advance\": false，继续在当前角色内讨论。\n"
                "输出 JSON 示例（未交接时）：\n"
                "```json\n"
                "{\n"
                '  "reply": "给用户的简短发言",\n'
                f'  "role": "{role}",\n'
                f'  "next_role": "{ROLE_REGISTRY[role]["next_default"]}",\n'
                '  "advance": false,\n'
                f'  "slot_name": "{ROLE_TO_SLOT[role]}",\n'
                '  "slot_value": "只在确认最终值时填写，若只是讨论则留空"\n'
                "}\n"
                "```\n"
                "【以上规则优先于你将要看到的 prompt 文件内容】\n\n"
            )
            base = runtime_rule + base
        return base

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
        user_confirmed: bool = False,
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
            "user_confirmed": user_confirmed,
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
        if context.get("user_confirmed"):
            parts.append("用户输入包含确认/推进信号（如“就这个”“下一步”“继续”），如果当前维度已经充分，请设置 advance: true 并交接给下一个专家。")
        parts.append(f"默认下一个角色：{context['next_default']}")
        parts.append("请按角色提示词要求输出 JSON。")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ #
    # LLM 调用与输出解析
    # ------------------------------------------------------------------ #
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM。

        system_prompt / user_prompt 都是已经渲染完成的最终字符串，其中包含
        JSON 示例、已收集槽位等字面花括号。ChatPromptTemplate 默认会把这些
        花括号当作模板变量解析，因此需要先转义为 {{ / }}。
        """
        from comedy_agent.models.factory import ModelFactory
        from langchain_core.prompts import ChatPromptTemplate

        system_prompt = system_prompt.replace("{", "{{").replace("}", "}}")
        user_prompt = user_prompt.replace("{", "{{").replace("}", "}}")

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
        current_state: str,
    ) -> str:
        """处理生成触发词。强制卡点：四槽位填满才能进入生成阶段。"""
        missing = [s for s in self.CORE_SLOTS if not slots.get(s)]
        if missing:
            next_role = SLOT_TO_ROLE.get(missing[0], "主持人")
            next_state = SLOT_TO_STATE.get(missing[0], "guiding")
            return json.dumps(
                {
                    "reply": f"⚠️ 还有以下维度未填写：{'、'.join(missing)}。请先补全后再生成。",
                    "next_role": next_role,
                    "slots_update": {},
                    "outputs_update": {},
                    "state_update": {"current_state": next_state},
                },
                ensure_ascii=False,
            )

        # 四维度已齐：进入询问生成方式状态
        return json.dumps(
            {
                "reply": "📝 四个维度已集齐。你希望「一次性生成」完整剧本，还是「按小节生成」逐段输出？",
                "next_role": "用户",
                "current_role": "总编",
                "state_update": {"current_state": "ask_generate_mode"},
            },
            ensure_ascii=False,
        )

    def _handle_ask_generate_mode(
        self,
        user_input: str,
        current_state: str,
        slots: dict[str, Any],
        outputs: dict[str, Any],
        user_id: str | None,
        attachments: list[dict[str, Any]],
    ) -> str:
        """解析用户选择的生成模式并直接生成内容。"""
        mode = self._parse_generate_mode(user_input)

        if mode == "one_shot":
            return self._handle_generate_one_shot(slots, outputs, user_id, attachments, current_state)

        if mode == "section":
            return self._handle_generate_section(
                slots, outputs, user_id, attachments, user_input, current_state
            )

        # 未识别，继续询问（带快捷按钮）
        return json.dumps(
            {
                "reply": "请选择生成方式：回复「一次性」生成完整剧本，或「按小节」逐段输出。",
                "next_role": "用户",
                "current_role": "总编",
                "next_actions": [
                    {"action": "set_generate_mode", "label": "📝 一次性生成", "value": "一次性"},
                    {"action": "set_generate_mode", "label": "📑 按小节生成", "value": "按小节"},
                ],
                "state_update": {"current_state": "ask_generate_mode"},
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _parse_generate_mode(user_input: str) -> str | None:
        """解析用户选择的生成模式。"""
        text = user_input.strip().lower()
        one_shot_keywords = ("一次性", "一次", "完整", "全部", "整体", "one", "全部生成")
        section_keywords = ("按小节", "小节", "分段", "逐段", "一节一节", "section", "一部分")

        # 先检查是否有明确否定词
        if any(k in text for k in one_shot_keywords) and "不" not in text[:10]:
            return "one_shot"
        if any(k in text for k in section_keywords) and "不" not in text[:10]:
            return "section"

        # 简短回复兜底
        if text in ("1", "一", "一次性"):
            return "one_shot"
        if text in ("2", "二", "按小节"):
            return "section"

        return None

    def _handle_generate_one_shot(
        self,
        slots: dict[str, Any],
        outputs: dict[str, Any],
        user_id: str | None,
        attachments: list[dict[str, Any]],
        current_state: str,
    ) -> str:
        """一次性生成完整剧本。"""
        final = self._generate_script_content(slots, outputs, user_id, attachments, section=None)

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
                "reply": "✅ 完整剧本已生成，请查看右侧工作台。",
                "next_role": "用户",
                "current_role": "总编",
                "state_update": {"current_state": "done"},
                "slots_update": {},
                "outputs_update": {"final_script": final, "script_main": final},
                "artifacts": [artifact],
            },
            ensure_ascii=False,
        )

    def _handle_generate_section(
        self,
        slots: dict[str, Any],
        outputs: dict[str, Any],
        user_id: str | None,
        attachments: list[dict[str, Any]],
        user_input: str,
        current_state: str,
    ) -> str:
        """按小节生成剧本。"""
        section_index = outputs.get("section_index", 0)
        section_outline = outputs.get("section_outline", [])
        generated_sections = outputs.get("generated_sections", [])

        # 第一次进入：生成章节大纲
        if not section_outline:
            section_outline = self._generate_section_outline(slots, attachments)
            outputs["section_outline"] = section_outline

        # 处理用户指令
        cmd = self._parse_section_command(user_input)
        if cmd == "finish":
            return json.dumps(
                {
                    "reply": "✅ 按小节生成已结束。完整剧本在右侧工作台。",
                    "next_role": "用户",
                    "current_role": "总编",
                    "state_update": {"current_state": "done"},
                    "slots_update": {},
                    "outputs_update": {"final_script": "\n\n".join(generated_sections), **outputs},
                },
                ensure_ascii=False,
            )

        if cmd == "retry" and section_index > 0:
            section_index -= 1
            generated_sections = generated_sections[:-1]

        if section_index >= len(section_outline):
            return json.dumps(
                {
                    "reply": "✅ 所有小节已生成完毕。回复「完成」结束，或继续补充修改。",
                    "next_role": "用户",
                    "current_role": "总编",
                    "state_update": {"current_state": "generating_section"},
                    "slots_update": {},
                    "outputs_update": outputs,
                },
                ensure_ascii=False,
            )

        section_title = section_outline[section_index]
        section_content = self._generate_script_content(
            slots, outputs, user_id, attachments, section=(section_index, section_title, section_outline, generated_sections)
        )
        generated_sections.append(f"## {section_title}\n\n{section_content}")

        # 更新 artifact（追加小节）
        full_script = "\n\n".join(generated_sections)
        artifact = {
            "id": "script_main",
            "type": "script",
            "title": "最终剧本",
            "content": f"## {section_title}\n\n{section_content}",
            "op": "create" if section_index == 0 and "script_main" not in outputs else "append",
            "version": (section_index + 1),
            "created_by": "总编",
        }

        next_index = section_index + 1
        outputs_update = {
            **outputs,
            "section_index": next_index,
            "generated_sections": generated_sections,
            "final_script": full_script,
            "script_main": full_script,
        }

        is_last = next_index >= len(section_outline)
        reply = f"✅ 第 {section_index + 1} 节「{section_title}」已生成。"
        actions = [
            {"action": "continue_section", "label": "▶️ 继续", "value": "继续"},
            {"action": "retry_section", "label": "🔄 修改上一节", "value": "修改"},
            {"action": "finish_section", "label": "✅ 完成", "value": "完成"},
        ]
        if is_last:
            reply += " 所有小节已完成，回复「完成」结束生成。"
        else:
            reply += " 回复「继续」生成下一节，或「修改」重生成本节。"

        return json.dumps(
            {
                "reply": reply,
                "next_role": "用户",
                "current_role": "总编",
                "next_actions": actions,
                "state_update": {"current_state": "generating_section"},
                "slots_update": {},
                "outputs_update": outputs_update,
                "artifacts": [artifact],
            },
            ensure_ascii=False,
        )

    def _handle_done_state(
        self,
        user_input: str,
        slots: dict[str, Any],
        outputs: dict[str, Any],
        user_id: str | None,
        attachments: list[dict[str, Any]],
        current_role: str,
    ) -> str:
        """已生成完成后的后续处理：修改、排版、保存等。"""
        text = user_input.strip().lower()

        if any(k in text for k in ("排版", "公众号", "小红书", "知乎", "b站")):
            return self._handle_tool_call("layout", user_input, slots, outputs, user_id, "排版专员", attachments)

        if any(k in text for k in ("修改", "重写", "再来")):
            return json.dumps(
                {
                    "reply": "📝 好的，请告诉我需要修改哪里，或者回复「重新生成」从头开始。",
                    "next_role": "用户",
                    "current_role": "总编",
                    "state_update": {"current_state": "done"},
                },
                ensure_ascii=False,
            )

        if any(k in text for k in ("重新生成", "再来一次")):
            # 清空已有输出，回到询问生成方式
            outputs.clear()
            return json.dumps(
                {
                    "reply": "📝 已清空之前的剧本。请选择生成方式：「一次性」或「按小节」。",
                    "next_role": "用户",
                    "current_role": "总编",
                    "state_update": {"current_state": "ask_generate_mode"},
                    "outputs_update": {"final_script": None, "script_main": None},
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "reply": "剧本已完成。你可以说「排版成公众号格式」或「修改某一部分」。",
                "next_role": "用户",
                "current_role": "总编",
                "state_update": {"current_state": "done"},
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _parse_section_command(user_input: str) -> str:
        """解析按小节生成时的用户指令。"""
        text = user_input.strip().lower()
        if any(k in text for k in ("完成", "结束", "done", "finish", "好了")):
            return "finish"
        if any(k in text for k in ("修改", "重来", "重生成", "retry", "上一节")):
            return "retry"
        if any(k in text for k in ("继续", "下一节", "next", "go on")):
            return "continue"
        # 默认继续
        return "continue"

    def _generate_section_outline(
        self,
        slots: dict[str, Any],
        attachments: list[dict[str, Any]],
    ) -> list[str]:
        """生成按小节创作的章节大纲。"""
        context_parts = [f"【{s}】{slots[s]}" for s in self.CORE_SLOTS]
        for att in attachments:
            full_text = att.get("full_text", "")
            summary = att.get("summary", "")
            display = summary if summary else (full_text[:500] + "..." if len(full_text) > 500 else full_text)
            context_parts.append(f"【{att.get('name', '参考')}】\n{display}")

        system_prompt = (
            "你是一位资深喜剧编剧。请根据以下创作维度，为剧本设计 3-5 个小节标题。"
            "只输出小节标题列表，每行一个，不要编号、不要解释。"
        )
        user_prompt = "创作维度：\n\n" + "\n\n".join(context_parts)

        try:
            outline_text = self._call_llm(system_prompt, user_prompt)
            outlines = [line.strip() for line in outline_text.strip().split("\n") if line.strip()]
            # 清理可能的编号前缀
            outlines = [re.sub(r"^\d+[.、]\s*", "", o) for o in outlines]
            return outlines[:6] or ["开场", "发展", "高潮", "结尾"]
        except Exception as e:
            logger.warning("生成章节大纲失败: %s", e)
            return ["开场", "发展", "高潮", "结尾"]

    def _generate_script_content(
        self,
        slots: dict[str, Any],
        outputs: dict[str, Any],
        user_id: str | None,
        attachments: list[dict[str, Any]],
        section: tuple[int, str, list[str], list[str]] | None = None,
    ) -> str:
        """调用 standup_generator 或 LLM 直接生成剧本内容。"""
        context_parts = [f"【{s}】{slots[s]}" for s in self.CORE_SLOTS]

        for att in attachments:
            full_text = att.get("full_text", "")
            summary = att.get("summary", "")
            display = summary if summary else (full_text[:800] + "..." if len(full_text) > 800 else full_text)
            context_parts.append(f"【{att.get('name', '参考')}】\n{display}")

        if section:
            idx, title, outline, previous = section
            context_parts.append(f"【当前小节】第 {idx + 1} 节：{title}")
            context_parts.append(f"【章节大纲】{' / '.join(outline)}")
            if previous:
                context_parts.append("【已生成内容】\n" + "\n\n".join(previous[-2:]))
            context_parts.append("请只输出当前小节的内容，不要输出其他小节的标题或内容。")

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

        return final

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

    _CONFIRMATION_WORDS: ClassVar[tuple[str, ...]] = (
        "就这个", "就按这个", "定下来了", "定稿", "确定", "确认", "就这样",
        "可以", "好的", "行", "没问题", "ok", "下一步", "继续", "推进",
    )

    _CONFIRMATION_NEGATIONS: ClassVar[tuple[str, ...]] = ("不", "没", "别", "否")

    @classmethod
    def _detect_confirmation(cls, user_input: str) -> bool:
        """判断用户输入是否为确认/推进信号。"""
        text = user_input.strip().lower()
        if not text:
            return False
        for kw in cls._CONFIRMATION_WORDS:
            idx = text.find(kw)
            if idx == -1:
                continue
            # 简单过滤否定前缀，如"不可以"、"不要继续"
            if idx > 0 and text[idx - 1] in cls._CONFIRMATION_NEGATIONS:
                continue
            return True
        return False
