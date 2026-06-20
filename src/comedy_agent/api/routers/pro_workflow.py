"""专业版 Wizard 工作流引擎 —— 状态机驱动的对话式分步生成。

基于 multi-prompt.md 建议，采用"状态机 + 单一路径"模式：
- 全局状态（current_state、slots、outputs）持久化在 Conversation.metadata
- 喜剧龙虾 skill 担任中央调度器，负责 collect / select / call / aggregate 四种动作
- 支持挂起等待用户输入，然后自动恢复
- 所有状态转移和 Skill 调用记录到 workflow_log 用于调试
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.billing import charge_model_usage, start_usage_tracking
from comedy_agent.api.state import state
from comedy_agent.api.routers.admin import require_admin
from comedy_agent.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pro"])

# ------------------------------------------------------------------ #
# 工作流持久化配置
# ------------------------------------------------------------------ #
_WORKFLOW_FILE = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "pro_workflow.json"

_DEFAULT_WORKFLOW: dict[str, Any] = {
    "initial_state": "guiding",
    "states": {
        "guiding": {
            "action": "guide",
            "role": "主持人",
            "message": "请按照流程表格的指引，@对应的写作团队成员完成创作。",
        },
        "topic_filling": {
            "action": "collect",
            "slot": "话题",
            "role": "话题专家",
            "message": "请描述你想创作的主题场景。",
        },
        "attitude_filling": {
            "action": "collect",
            "slot": "态度",
            "role": "态度专家",
            "message": "请给出你对这个话题的态度。",
        },
        "bias_filling": {
            "action": "collect",
            "slot": "偏见",
            "role": "偏见专家",
            "message": "请给出一个独特视角或偏见。",
        },
        "emotion_filling": {
            "action": "collect",
            "slot": "情绪",
            "role": "情绪专家",
            "message": "请描述情感节奏变化。",
        },
        "ask_generate_mode": {
            "action": "ask",
            "role": "总编",
            "message": "四个维度已集齐。你希望一次性生成完整剧本，还是按小节逐段生成？",
        },
        "generating_one_shot": {
            "action": "generate",
            "mode": "one_shot",
            "role": "总编",
            "message": "正在生成完整剧本...",
        },
        "generating_section": {
            "action": "generate",
            "mode": "section",
            "role": "总编",
            "message": "正在按小节生成剧本...",
        },
        "done": {
            "action": "done",
            "role": "总编",
            "message": "剧本已生成完成。",
        },
    },
    "transitions": {
        "guiding": {"next": "guiding"},
        "topic_filling": {"next": "attitude_filling"},
        "attitude_filling": {"next": "bias_filling"},
        "bias_filling": {"next": "emotion_filling"},
        "emotion_filling": {"next": "ask_generate_mode"},
        "ask_generate_mode": {"next": None},
        "generating_one_shot": {"next": "done"},
        "generating_section": {"next": "generating_section"},
        "done": {"next": None},
    },
}


# ------------------------------------------------------------------ #
# 兼容旧版工作流（线性步骤列表 -> 状态机）
# ------------------------------------------------------------------ #
def _migrate_legacy_workflow(data: Any) -> dict[str, Any]:
    """将旧版步骤列表迁移为状态机结构。"""
    if isinstance(data, dict) and "states" in data and "transitions" in data:
        return data

    if not isinstance(data, list) or len(data) == 0:
        return dict(_DEFAULT_WORKFLOW)

    states: dict[str, Any] = {}
    transitions: dict[str, Any] = {}

    for i, step in enumerate(data):
        step_id = step.get("id", f"step_{i}")
        step_type = step.get("type", "skill")
        state_cfg: dict[str, Any] = {"message": step.get("message", "")}

        if step_type == "validation":
            state_cfg["action"] = "collect"
            state_cfg["slot"] = step.get("field", "outline")
        elif step_type == "selection":
            state_cfg["action"] = "select"
            state_cfg["skill_type"] = step.get("skill_type", "")
        elif step_type == "skill":
            if step.get("is_final"):
                state_cfg["action"] = "aggregate"
            else:
                state_cfg["action"] = "call"
                state_cfg["skill"] = step.get("skill", "")
        else:
            state_cfg["action"] = "collect"
            state_cfg["slot"] = "outline"

        states[step_id] = state_cfg

        # 构建 transitions
        if i + 1 < len(data):
            next_id = data[i + 1].get("id", f"step_{i + 1}")
            transitions[step_id] = {"next": next_id}
        else:
            transitions[step_id] = {"next": None}

    return {
        "initial_state": data[0].get("id", "step_0") if data else "step_0",
        "states": states,
        "transitions": transitions,
    }


# ------------------------------------------------------------------ #
# 加载 / 保存工作流
# ------------------------------------------------------------------ #
def _load_workflow() -> dict[str, Any]:
    """从 JSON 文件加载工作流配置，不存在则写入默认配置。"""
    if _WORKFLOW_FILE.exists():
        try:
            with _WORKFLOW_FILE.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            return _migrate_legacy_workflow(raw)
        except Exception as e:
            logger.warning("工作流配置文件读取失败，使用默认配置: %s", e)

    try:
        _WORKFLOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _WORKFLOW_FILE.open("w", encoding="utf-8") as f:
            json.dump(_DEFAULT_WORKFLOW, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("工作流配置文件写入失败: %s", e)

    return dict(_DEFAULT_WORKFLOW)


def _save_workflow(config: dict[str, Any]) -> None:
    """保存工作流配置到 JSON 文件。"""
    try:
        _WORKFLOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _WORKFLOW_FILE.open("w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("工作流配置文件保存失败: %s", e)
        raise HTTPException(status_code=500, detail="工作流保存失败")


# ------------------------------------------------------------------ #
# 请求 / 响应模型
# ------------------------------------------------------------------ #
class ProChatRequest(BaseModel):
    """专业版对话请求。"""

    session_id: str | None = Field(default=None, description="会话 ID，为空则新建")
    message: str = Field(description="用户消息")
    outline: str | None = Field(default=None, description="选题大纲（兼容旧字段）")
    persona_id: str | None = Field(default=None, description="人物画像 ID")
    model: str | None = Field(default=None, description="使用的模型名称")


class Artifact(BaseModel):
    """工作台（Artifacts）中的内容单元。"""

    id: str = Field(description="artifact 唯一 ID")
    type: str = Field(description="类型：outline / research / script / review / section")
    title: str = Field(description="标题")
    content: str = Field(description="内容")
    op: str = Field(default="create", description="操作：create / append / update")
    version: int = Field(default=1, description="版本号")
    created_by: str = Field(description="生成该内容的角色名")


class Attachment(BaseModel):
    """角色间传递的附件。"""

    id: str = Field(description="附件唯一 ID")
    name: str = Field(description="附件名称")
    summary: str = Field(default="", description="长文档摘要")
    full_text: str = Field(description="全文内容")
    mime_type: str = Field(default="text/plain", description="MIME 类型")


class TodoItem(BaseModel):
    """TODO 看板条目。"""

    id: str = Field(description="条目 ID")
    label: str = Field(description="显示文本")
    done: bool = Field(default=False, description="是否完成")
    optional: bool = Field(default=False, description="是否可选")
    blocked: bool = Field(default=False, description="是否被阻塞")
    role: str | None = Field(default=None, description="负责角色")


class ProChatResponse(BaseModel):
    """专业版对话响应。"""

    session_id: str = Field(description="会话 ID")
    type: str = Field(description="响应类型：guide / skill_output / final_script / error")
    content: str = Field(description="响应内容")
    workflow_state: str = Field(description="当前工作流状态")
    skill_name: str | None = Field(default=None, description="当前调用的 Skill 名称")
    current_role: str | None = Field(default=None, description="当前发言角色")
    next_role: str | None = Field(default=None, description="下一个该发言的角色")
    next_actions: list[dict[str, Any]] | None = Field(
        default=None, description="下一步可执行操作"
    )
    steps: list[dict[str, Any]] | None = Field(
        default=None, description="链式执行的所有步骤"
    )
    checklist: list[dict[str, Any]] | None = Field(
        default=None, description="当前流程检查清单"
    )
    todo_board: list[TodoItem] | None = Field(
        default=None, description="结构化 TODO 看板"
    )
    slots: dict[str, Any] | None = Field(
        default=None, description="当前已收集的槽位"
    )
    artifacts: list[Artifact] | None = Field(
        default=None, description="工作台内容更新"
    )
    attachments: list[Attachment] | None = Field(
        default=None, description="角色间传递的附件"
    )


# ------------------------------------------------------------------ #
# 工作流引擎（状态机）
# ------------------------------------------------------------------ #
class ProWorkflowEngine:
    """专业版状态机工作流引擎。

    维护状态：current_state、slots、outputs、log
    每次用户消息触发 喜剧龙虾 调度器，执行当前状态对应的动作。
    """

    # 核心工作流程维度（由 喜剧龙虾 内部处理，不直接调用外部 Skill）
    _CORE_SLOTS: ClassVar[tuple[str, ...]] = ("话题", "态度", "偏见", "情绪")

    # 前端展示名称 -> Skill 注册名（处理 @素材 / @排版 等中文 mention）
    _DISPLAY_TO_SKILL_NAME: ClassVar[dict[str, str]] = {
        "素材": "material",
        "排版": "layout",
        "风格": "genre",
    }

    def __init__(self, orch: Any, memory: Any, workflow: dict[str, Any] | None = None) -> None:
        self.orch = orch
        self.memory = memory
        self.workflow = workflow or dict(_DEFAULT_WORKFLOW)

    def process(
        self,
        session_id: str | None,
        user_id: str,
        message: str,
        outline: str | None,
        persona_id: str | None,
        model: str | None,
    ) -> dict[str, Any]:
        """处理用户消息，返回响应。

        新架构：喜剧龙虾 skill 内部处理核心工作流程（话题/态度/偏见/情绪），
        引擎层不再依赖严格的状态机，始终调用 喜剧龙虾 skill 进行调度。
        """
        # 0. 开始追踪模型用量
        start_usage_tracking()

        # 1. 加载或创建会话
        conv = None
        if session_id:
            conv = self.memory.load_conversation(user_id, session_id)

        if conv is None:
            session_id = uuid.uuid4().hex[:16]
            wf_state = self._init_state()
            messages: list[dict[str, Any]] = []
            if outline:
                wf_state["slots"]["outline"] = outline
            if persona_id:
                wf_state["slots"]["persona_id"] = persona_id
        else:
            session_id = conv.session_id
            wf_state = (conv.metadata or {}).get("workflow", {}) if conv.metadata else {}
            if not wf_state:
                wf_state = self._init_state()
                if outline:
                    wf_state["slots"]["outline"] = outline
                if persona_id:
                    wf_state["slots"]["persona_id"] = persona_id
            messages = list(conv.messages) if conv.messages else []

        # 2. 添加用户消息到会话
        messages.append({"role": "human", "content": message})

        # 3. 初始化 steps 数组
        steps: list[dict[str, Any]] = []

        # 4. 自动应用人物画像（如果已选择且尚未应用）
        if persona_id and "rule_persona" not in wf_state.get("outputs", {}):
            persona_result = self._call_skill_direct("rule_persona", wf_state, user_id)
            if persona_result and not persona_result["reply"].startswith("❌"):
                wf_state.setdefault("outputs", {})["rule_persona"] = persona_result["output"]
                steps.append({
                    "type": "skill_output",
                    "content": persona_result["reply"],
                    "skill_name": "rule_persona",
                })
                messages.append({"role": "ai", "content": persona_result["reply"]})

        # 5. 检测 @mention 外部 Skill（排除 喜剧龙虾 和核心维度）
        mention = self._detect_mention(message)
        if mention and mention not in ("get_daren", "Get达人", "喜剧龙虾") and mention not in self._CORE_SLOTS:
            # 直接调用外部 Skill（场景、写手、找茬等）
            skill_result = self._call_skill_direct(mention, wf_state, user_id, message=message)
            if skill_result:
                if skill_result.get("output"):
                    wf_state.setdefault("outputs", {})[mention] = skill_result["output"]
                # 直接展示 Skill 实际输出（如素材、排版结果），而非仅展示调用提示
                display_content = skill_result.get("output") or skill_result.get("reply", "")
                steps.append({
                    "type": "skill_output",
                    "content": display_content,
                    "skill_name": mention,
                })
                messages.append({"role": "ai", "content": skill_result.get("reply", "")})
                checklist = self._build_checklist(wf_state)
                return self._build_response(session_id, wf_state, steps, checklist, messages, message, persona_id, user_id)

        # 6. 调用 喜剧龙虾 skill（核心维度、生成指令、无 @mention 均走这里）
        # 根据当前状态机状态选择对应配置
        current_state_id = wf_state.get("current_state", self.workflow.get("initial_state", "guiding"))
        state_cfg = dict(self.workflow.get("states", {}).get(current_state_id, {"action": "guide"}))
        state_cfg["state_id"] = current_state_id
        result = self._execute_state(state_cfg, wf_state, message, user_id, messages)

        # 7. 更新 slots/outputs / current_role / artifacts / attachments / current_state
        if result.get("slots_update"):
            wf_state.setdefault("slots", {}).update(result["slots_update"])
        if result.get("outputs_update"):
            wf_state.setdefault("outputs", {}).update(result["outputs_update"])
        if result.get("role"):
            wf_state["current_role"] = result["role"]
        if result.get("state_update"):
            wf_state.update(result["state_update"])
        if result.get("artifacts"):
            wf_state.setdefault("artifacts", []).extend(result["artifacts"])
        if result.get("attachments"):
            wf_state.setdefault("attachments", []).extend(result["attachments"])

        # 8. 记录日志
        wf_state.setdefault("log", []).append({
            "state": wf_state.get("current_state", "guiding"),
            "action": "guide",
            "input": message,
            "output": result.get("reply", "")[:200],
        })

        # 9. 添加 AI 回复
        reply = result.get("reply", "")
        messages.append({"role": "ai", "content": reply})

        # 10. 确定响应类型
        if "final_script" in result.get("outputs_update", {}):
            response_type = "final_script"
            # 若后端未显式指定下一状态，则默认为 done
            if not result.get("state_update", {}).get("current_state"):
                wf_state["current_state"] = "done"
        else:
            response_type = "guide"

        # 11. 构建 checklist 和 todo_board
        checklist = self._build_checklist(wf_state)
        todo_board = self._build_todo_board(wf_state.get("slots", {}))
        wf_state["todo_board"] = todo_board

        steps.append({
            "type": response_type,
            "content": reply,
            "skill_name": "get_daren",
            "checklist": checklist,
            "todo_board": todo_board,
            "current_role": wf_state.get("current_role"),
            "next_role": result.get("next_role"),
            "artifacts": result.get("artifacts", []),
            "attachments": result.get("attachments", []),
        })

        # 12. 保存会话并返回
        return self._build_response(session_id, wf_state, steps, checklist, messages, message, persona_id, user_id)

    def load_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        """加载会话及工作流状态。"""
        conv = self.memory.load_conversation(user_id, session_id)
        if conv is None:
            return None
        wf_state = (conv.metadata or {}).get("workflow", {}) if conv.metadata else {}
        return {
            "session_id": conv.session_id,
            "messages": conv.messages,
            "workflow_state": wf_state.get("current_state", self.workflow.get("initial_state", "")),
            "metadata": conv.metadata,
        }

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #
    def _init_state(self) -> dict[str, Any]:
        return {
            "current_state": self.workflow.get("initial_state", ""),
            "current_role": "主持人",
            "slots": {},
            "outputs": {},
            "attachments": [],
            "decision_nodes": [],
            "todo_board": self._build_todo_board({}),
            "log": [],
        }

    def _build_todo_board(self, slots: dict[str, Any]) -> list[dict[str, Any]]:
        """根据核心槽位构建 TODO 看板。"""
        return [
            {"id": "话题", "label": "话题", "done": bool(slots.get("话题")), "optional": False, "blocked": False, "role": "话题专家"},
            {"id": "态度", "label": "态度", "done": bool(slots.get("态度")), "optional": False, "blocked": not bool(slots.get("话题")), "role": "态度专家"},
            {"id": "偏见", "label": "偏见", "done": bool(slots.get("偏见")), "optional": False, "blocked": not bool(slots.get("态度")), "role": "偏见专家"},
            {"id": "情绪", "label": "情绪", "done": bool(slots.get("情绪")), "optional": False, "blocked": not bool(slots.get("偏见")), "role": "情绪专家"},
            {"id": "aggregate", "label": "生成最终剧本", "done": False, "optional": False, "blocked": not all(slots.get(s) for s in self._CORE_SLOTS), "role": "总编"},
        ]

    def _execute_state(
        self,
        state_cfg: dict[str, Any],
        wf_state: dict[str, Any],
        user_input: str,
        user_id: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """调用 喜剧龙虾 skill 执行当前状态动作。"""
        if self.orch is None:
            return {"reply": "服务未就绪", "advance": False}

        try:
            skill = self.orch._find_skill("get_daren")
            if skill is None:
                return {"reply": "❌ 喜剧龙虾 skill 未注册", "advance": False}
        except Exception as e:
            return {"reply": f"❌ 查找 喜剧龙虾 skill 失败：{e}", "advance": False}

        try:
            result = skill.invoke(
                {
                    "workflow_step": state_cfg,
                    "slots": wf_state.get("slots", {}),
                    "outputs": wf_state.get("outputs", {}),
                    "user_input": user_input,
                    "conversation_history": messages[:-1][-10:],
                    "user_id": user_id,
                    "current_role": wf_state.get("current_role", "主持人"),
                    "attachments": wf_state.get("attachments", []),
                    "decision_nodes": wf_state.get("decision_nodes", []),
                }
            )
        except Exception as e:
            logger.error("喜剧龙虾执行失败: %s", e, exc_info=True)
            return {"reply": f"❌ 调度失败：{e}", "advance": False}

        # 解析 喜剧龙虾 返回的 JSON
        parsed = self._parse_daren_result(result)

        # 更新 slots 和 outputs
        if parsed.get("slots_update"):
            wf_state.setdefault("slots", {}).update(parsed["slots_update"])
        if parsed.get("outputs_update"):
            wf_state.setdefault("outputs", {}).update(parsed["outputs_update"])

        return parsed

    def _parse_daren_result(self, result: Any) -> dict[str, Any]:
        """解析 喜剧龙虾 skill 返回的结果。"""
        raw = ""
        if isinstance(result, dict):
            raw = result.get("output", "")
        elif isinstance(result, str):
            raw = result
        else:
            raw = str(result)

        # 先尝试作为 JSON 解析
        if raw.strip().startswith("{"):
            try:
                data = json.loads(raw)
                return {
                    "reply": data.get("reply", raw),
                    "advance": bool(data.get("advance", False)),
                    "slots_update": data.get("slots_update", {}),
                    "outputs_update": data.get("outputs_update", {}),
                    "role": data.get("role"),
                    "next_role": data.get("next_role"),
                    "artifacts": data.get("artifacts", []),
                    "attachments": data.get("attachments", []),
                    "state_update": data.get("state_update", {}),
                }
            except json.JSONDecodeError:
                pass

        return {
            "reply": raw,
            "advance": False,
            "slots_update": {},
            "outputs_update": {},
            "role": None,
            "next_role": None,
            "artifacts": [],
            "attachments": [],
            "state_update": {},
        }

    def _build_select_actions(self, state_cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """为 select 动作构建选项按钮。"""
        skill_type = state_cfg.get("skill_type", "")
        actions = []
        if self.orch:
            for info in self.orch.list_skills():
                name = info.get("name", "")
                inferred = "other"
                if "topic" in name:
                    inferred = "topic"
                elif "attitude" in name:
                    inferred = "attitude"
                elif "emotion" in name:
                    inferred = "emotion"
                elif "genre" in name:
                    inferred = "genre"
                elif "rule_persona" in name:
                    inferred = "rule_persona"
                elif "script_composer" in name:
                    inferred = "script_composer"

                if inferred == skill_type:
                    actions.append(
                        {"action": "select_skill", "label": name, "value": name}
                    )
        return actions

    # ------------------------------------------------------------------ #
    # @mention 检测与 Skill 直接调用
    # ------------------------------------------------------------------ #
    @staticmethod
    def _detect_mention(message: str) -> str | None:
        """检测用户消息中的 @mention，返回 skill 名。"""
        import re
        match = re.search(r"@(\S+)", message)
        if match:
            return match.group(1)
        return None

    def _call_skill_direct(
        self,
        skill_name: str,
        wf_state: dict[str, Any],
        user_id: str,
        message: str = "",
    ) -> dict[str, Any] | None:
        """直接调用指定 Skill（绕过 喜剧龙虾）。"""
        if self.orch is None:
            return None

        # 中文展示名映射为 Skill 注册名，便于 Orchestrator 直接定位 Tool
        display_name = skill_name
        canonical_name = self._DISPLAY_TO_SKILL_NAME.get(skill_name, skill_name)

        slots = wf_state.get("slots", {})
        outputs = wf_state.get("outputs", {})

        # 构建 prompt（复用原 _action_call 中的 prompt 构建逻辑）
        current_text = outputs.get("outline") or slots.get("outline", "")
        for key in ["topic", "attitude", "emotion"]:
            if key in outputs:
                current_text = outputs[key]

        # 提取用户消息中除 @mention 之外的实际查询词
        user_query = message
        mention_match = re.search(r"@(\S+)", message)
        if mention_match:
            user_query = message[: mention_match.start()] + message[mention_match.end() :]
        user_query = user_query.strip("，,。. ")

        if skill_name == "rule_persona":
            persona_id = slots.get("persona_id", "")
            memory = getattr(self, "memory", None)
            rule_content = ""
            persona_name = ""
            if memory and persona_id:
                persona = memory.load_persona(persona_id)
                if persona:
                    rule_content = getattr(persona, "rule_content", {})
                    persona_name = getattr(persona, "name", "")
            if not persona_id:
                return {
                    "reply": "🎭 你尚未选择人物画像，请先点击写作团队按钮选择一个画像。",
                    "output": "",
                    "skill_name": skill_name,
                }
            prompt = (
                f"使用 rule_persona 技能。\n"
                f"大纲：{current_text}\n"
                f"规则：{rule_content}"
            )
            reply_msg = f"🎭 正在应用人物画像「{persona_name}」的规则约束..." if persona_name else "🎭 正在应用人物画像规则..."
        elif skill_name == "script_composer":
            context_parts = [f"大纲：{slots.get('outline', '')}"]
            for key, val in outputs.items():
                if key != "outline":
                    context_parts.append(f"【{key} 输出】\n{val}")
            context_text = "\n\n".join(context_parts)
            prompt = f"使用 script_composer 技能。\n上下文：\n{context_text}"
            reply_msg = "📝 正在生成剧本..."
        elif canonical_name == "material":
            # 素材搜索优先使用用户输入的查询词，避免与工作流 outline 混淆
            prompt = (
                f"使用 {canonical_name} 技能。\n"
                f"搜索词：{user_query}"
            )
            reply_msg = f"🔍 正在调用 {display_name} 专家搜索「{user_query}」..."
        elif canonical_name == "layout":
            # 排版 skill：优先处理用户查询意图；若用户只是咨询平台/格式，直接返回帮助信息
            # 若用户要求排版「最终结果」，则必须使用已生成的 final_script
            from comedy_agent.skills.layout import LayoutSkill

            if LayoutSkill._is_consultation(user_query):
                return {
                    "reply": f"🔍 正在调用 {display_name} 专家...",
                    "output": LayoutSkill._platform_help(),
                    "skill_name": canonical_name,
                }

            # 判断用户是否明确要求排版最终剧本
            wants_final = LayoutSkill._is_final_result_request(user_query)
            final_script = outputs.get("final_script", "")

            # 待排版正文：最终结果 > 当前维度输出/outline > 用户直接输入的内容
            if wants_final:
                if not final_script:
                    return {
                        "reply": "📝 你还没有生成最终剧本，请回复「生成」生成最终剧本后再进行排版。",
                        "output": "",
                        "skill_name": canonical_name,
                    }
                content_to_layout = final_script
            else:
                content_to_layout = current_text or user_query

            if not content_to_layout:
                return {
                    "reply": "📝 请提供需要排版的内容，或问我「可以排成什么样的？」了解支持的平台。",
                    "output": "",
                    "skill_name": canonical_name,
                }

            platform = LayoutSkill._extract_platform_from_query(user_query) or "wechat"

            # 直接调用 layout skill，避免 LLM 参数提取阶段把指令文字误当正文
            skill = self.orch._find_skill(canonical_name)
            if skill is None:
                return {
                    "reply": f"❌ {display_name} skill 未注册",
                    "output": "",
                    "skill_name": canonical_name,
                }
            try:
                output = skill.invoke({"text": content_to_layout, "platform": platform})
                return {
                    "reply": f"🔍 正在调用 {display_name} 专家...",
                    "output": output,
                    "skill_name": canonical_name,
                }
            except Exception as e:
                logger.error("排版 Skill 直接调用失败: %s", e, exc_info=True)
                return {
                    "reply": f"❌ {display_name} 调用失败：{e}",
                    "output": "",
                    "skill_name": canonical_name,
                }
        else:
            prompt = f"使用 {canonical_name} 技能。\n文本：{current_text}"
            reply_msg = f"🔍 正在调用 {display_name} 专家..."

        try:
            result = self.orch.run(prompt, user_id=user_id)
            output = result.get("output", "")
        except Exception as e:
            logger.error("Skill 直接调用失败: %s", e, exc_info=True)
            return {
                "reply": f"❌ {display_name} 调用失败：{e}",
                "output": "",
                "skill_name": canonical_name,
            }

        return {
            "reply": reply_msg,
            "output": output,
            "skill_name": canonical_name,
        }

    # ------------------------------------------------------------------ #
    # Checklist 生成与格式化
    # ------------------------------------------------------------------ #
    def _build_checklist(self, wf_state: dict[str, Any]) -> list[dict[str, Any]]:
        """根据核心槽位构建流程检查清单。"""
        slots = wf_state.get("slots", {})
        outputs = wf_state.get("outputs", {})
        return [
            {"id": "话题",     "label": "话题", "done": bool(slots.get("话题")),     "optional": False},
            {"id": "态度",     "label": "态度", "done": bool(slots.get("态度")),     "optional": False},
            {"id": "偏见",     "label": "偏见", "done": bool(slots.get("偏见")),     "optional": False},
            {"id": "情绪",     "label": "情绪", "done": bool(slots.get("情绪")),     "optional": False},
            {"id": "aggregate","label": "生成最终剧本", "done": "final_script" in outputs, "optional": False},
        ]


    def _format_checklist(checklist: list[dict[str, Any]]) -> str:
        """将 checklist 格式化为带勾的文本。"""
        lines = ["📋 创作流程："]
        for item in checklist:
            mark = "✅" if item["done"] else "⬜"
            lines.append(f"{mark} {item['label']}")
        return "\n".join(lines)


    def _build_next_hint_from_checklist(checklist: list[dict[str, Any]]) -> str:
        """根据 checklist 构建下一步提示。"""
        # 找到第一个未完成的必要步骤
        next_item = next(
            (item for item in checklist if not item["done"] and not item.get("optional")),
            None
        )
        if next_item:
            if next_item["id"] == "aggregate":
                return '👉 所有维度已填写完成！请回复"生成"来生成最终剧本。'
            return f"👉 下一步：请 @{next_item['id']} 输入相关内容。"

        return '👉 所有维度已填写完成！请回复"生成"来生成最终剧本。'

    def _build_response(
        self,
        session_id: str,
        wf_state: dict[str, Any],
        steps: list[dict[str, Any]],
        checklist: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        user_message: str,
        persona_id: str | None,
        user_id: str,
    ) -> dict[str, Any]:
        """构建并返回最终响应。"""
        # 同步更新 TODO 看板
        wf_state["todo_board"] = self._build_todo_board(wf_state.get("slots", {}))

        metadata = {"workflow": wf_state}
        if persona_id:
            metadata["persona_id"] = persona_id
        self.memory.save_conversation(
            user_id=user_id,
            session_id=session_id,
            messages=messages,
            summary=user_message[:40] + "…" if len(user_message) > 40 else user_message,
            source="pro",
            metadata=metadata,
        )

        last_step = steps[-1] if steps else {"type": "guide", "content": "", "skill_name": None, "next_actions": None, "checklist": None, "artifacts": None, "attachments": None, "next_role": None}

        return {
            "session_id": session_id,
            "type": last_step.get("type", "guide"),
            "content": last_step.get("content", ""),
            "workflow_state": wf_state.get("current_state", "done"),
            "skill_name": last_step.get("skill_name"),
            "current_role": wf_state.get("current_role"),
            "next_role": last_step.get("next_role") or wf_state.get("current_role"),
            "next_actions": last_step.get("next_actions"),
            "checklist": last_step.get("checklist") or checklist,
            "todo_board": wf_state.get("todo_board", []),
            "steps": steps,
            "slots": wf_state.get("slots", {}),
            "artifacts": last_step.get("artifacts") or [],
            "attachments": wf_state.get("attachments", []),
        }

    @staticmethod
    def _error_response(session_id: str, state: str, content: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "type": "error",
            "content": content,
            "workflow_state": state,
            "skill_name": None,
            "next_actions": None,
        }


# ------------------------------------------------------------------ #
# 全局引擎实例（lazy init）
# ------------------------------------------------------------------ #
_workflow_engine: ProWorkflowEngine | None = None


def _get_engine() -> ProWorkflowEngine:
    global _workflow_engine
    if _workflow_engine is None:
        if state.orch is None or state.memory is None:
            raise HTTPException(status_code=503, detail="服务未就绪")
        workflow = _load_workflow()
        _workflow_engine = ProWorkflowEngine(
            orch=state.orch, memory=state.memory, workflow=workflow
        )
    return _workflow_engine


# ------------------------------------------------------------------ #
# API 端点
# ------------------------------------------------------------------ #
@router.post("/pro/chat", response_model=ProChatResponse)
async def pro_chat(
    request: ProChatRequest,
    user_id: str = Depends(get_current_user),
) -> ProChatResponse:
    """专业版 Wizard 对话入口。

    接收用户消息，推进工作流状态机，返回引导消息或 Skill 输出。
    """
    engine = _get_engine()

    # 模型切换：专业版默认使用 deepseek-v4-pro，用户可显式覆盖
    if state.orch:
        state.orch.set_model(request.model or "deepseek-v4-pro")

    result = engine.process(
        session_id=request.session_id,
        user_id=user_id,
        message=request.message,
        outline=request.outline,
        persona_id=request.persona_id,
        model=request.model,
    )
    charge_model_usage(
        user_id=user_id,
        endpoint="/pro/chat",
        description="专业版 Wizard 对话",
        session_id=result.get("session_id"),
        fallback_cost=5,
    )
    return ProChatResponse(**result)


@router.get("/pro/chat/{session_id}")
async def pro_chat_load(
    session_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """加载专业版 Wizard 会话状态。"""
    engine = _get_engine()
    data = engine.load_session(user_id, session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return data


# ------------------------------------------------------------------ #
# Admin 工作流管理 API
# ------------------------------------------------------------------ #
class WorkflowState(BaseModel):
    """状态机中的单个状态。"""

    action: str = Field(description="动作类型：collect / select / call / aggregate")
    message: str = Field(description="该状态下的引导/提示消息")
    slot: str | None = Field(default=None, description="collect 动作对应的槽位名")
    skill_type: str | None = Field(default=None, description="select 动作对应的 skill 分类")
    skill: str | None = Field(default=None, description="call 动作调用的 skill 名称")


class WorkflowTransition(BaseModel):
    """状态转移配置。"""

    next: str | None = Field(default=None, description="下一个状态 id，null 表示结束")


class WorkflowConfig(BaseModel):
    """完整工作流配置。"""

    initial_state: str = Field(description="初始状态 id")
    states: dict[str, WorkflowState] = Field(description="所有状态定义")
    transitions: dict[str, WorkflowTransition] = Field(description="状态转移表")


@router.get("/admin/workflow", response_model=WorkflowConfig)
async def admin_get_workflow(
    _admin: str = Depends(require_admin),
) -> WorkflowConfig:
    """获取当前专业版工作流配置（仅管理员）。"""
    config = _load_workflow()
    return WorkflowConfig(**config)


@router.put("/admin/workflow")
async def admin_update_workflow(
    request: WorkflowConfig,
    _admin: str = Depends(require_admin),
) -> dict[str, bool]:
    """更新专业版工作流配置（仅管理员）。"""
    config = request.model_dump()

    # 校验
    states = config.get("states", {})
    transitions = config.get("transitions", {})
    initial_state = config.get("initial_state", "")

    if not states:
        raise HTTPException(status_code=400, detail="states 不能为空")
    if initial_state not in states:
        raise HTTPException(status_code=400, detail="initial_state 必须存在于 states")

    valid_actions = {"collect", "select", "call", "aggregate"}
    for state_id, s in states.items():
        action = s.get("action", "")
        if action not in valid_actions:
            raise HTTPException(status_code=400, detail=f"状态 {state_id} 的 action 非法")
        if action == "collect" and not s.get("slot"):
            raise HTTPException(status_code=400, detail=f"状态 {state_id} 为 collect 但缺少 slot")
        if action == "select" and not s.get("skill_type"):
            raise HTTPException(status_code=400, detail=f"状态 {state_id} 为 select 但缺少 skill_type")
        if action == "call" and not s.get("skill"):
            raise HTTPException(status_code=400, detail=f"状态 {state_id} 为 call 但缺少 skill")

    for state_id in states:
        if state_id not in transitions:
            raise HTTPException(status_code=400, detail=f"状态 {state_id} 缺少 transition")

    _save_workflow(config)

    # 刷新引擎实例
    global _workflow_engine
    _workflow_engine = None

    return {"success": True}
