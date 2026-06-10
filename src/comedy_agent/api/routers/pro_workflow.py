"""专业版 Wizard 工作流引擎 —— 状态机驱动的对话式分步生成。

基于 multi-prompt.md 建议，采用"状态机 + 单一路径"模式：
- 全局状态（current_state、slots、outputs）持久化在 Conversation.metadata
- Get达人 skill 担任中央调度器，负责 collect / select / call / aggregate 四种动作
- 支持挂起等待用户输入，然后自动恢复
- 所有状态转移和 Skill 调用记录到 workflow_log 用于调试
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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
    "initial_state": "awaiting_outline",
    "states": {
        "awaiting_outline": {
            "action": "collect",
            "slot": "outline",
            "message": "📋 你好，我是 Get达人。请告诉我你想创作什么内容？一句话描述主题即可，例如：实习生被领导刁难后逆袭的职场段子。",
        },
        "awaiting_genre": {
            "action": "select",
            "skill_type": "genre",
            "message": "🎭 请选择剧本体裁，这将决定整体的创作风格。",
        },
        "calling_topic": {
            "action": "call",
            "skill": "topic",
            "message": "🔍 正在调用话题专家扩写话题背景与冲突点...",
        },
        "calling_attitude": {
            "action": "call",
            "skill": "attitude",
            "message": "🎯 正在调用态度专家注入态度...",
        },
        "calling_emotion": {
            "action": "call",
            "skill": "emotion",
            "message": "💫 正在调用情绪专家调整情绪节奏...",
        },
        "calling_rule_persona": {
            "action": "call",
            "skill": "rule_persona",
            "message": "🎭 正在应用人物画像规则...",
        },
        "aggregating": {
            "action": "aggregate",
            "message": "📝 正在汇总各专家意见，生成最终剧本...",
        },
    },
    "transitions": {
        "awaiting_outline": {"next": "awaiting_genre"},
        "awaiting_genre": {"next": "calling_topic"},
        "calling_topic": {"next": "calling_attitude"},
        "calling_attitude": {"next": "calling_emotion"},
        "calling_emotion": {"next": "calling_rule_persona"},
        "calling_rule_persona": {"next": "aggregating"},
        "aggregating": {"next": None},
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


class ProChatResponse(BaseModel):
    """专业版对话响应。"""

    session_id: str = Field(description="会话 ID")
    type: str = Field(description="响应类型：guide / skill_output / final_script / error")
    content: str = Field(description="响应内容")
    workflow_state: str = Field(description="当前工作流状态")
    skill_name: str | None = Field(default=None, description="当前调用的 Skill 名称")
    next_actions: list[dict[str, Any]] | None = Field(
        default=None, description="下一步可执行操作"
    )


# ------------------------------------------------------------------ #
# 工作流引擎（状态机）
# ------------------------------------------------------------------ #
class ProWorkflowEngine:
    """专业版状态机工作流引擎。

    维护状态：current_state、slots、outputs、log
    每次用户消息触发 Get达人调度器，执行当前状态对应的动作。
    """

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
        """处理用户消息，推进状态机，返回响应。"""
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

        # 3. 获取当前状态配置
        current_state = wf_state.get("current_state", self.workflow.get("initial_state", ""))
        state_cfg = self.workflow.get("states", {}).get(current_state)

        if state_cfg is None:
            return self._error_response(session_id, current_state, f"未知工作流状态：{current_state}")

        # 4. 调用 Get达人 skill 执行当前状态动作
        result = self._execute_state(state_cfg, wf_state, message, user_id)

        # 5. 推进状态
        if result.get("advance", False):
            transitions = self.workflow.get("transitions", {})
            next_state = transitions.get(current_state, {}).get("next")
            if next_state:
                wf_state["current_state"] = next_state
            else:
                wf_state["current_state"] = "done"

        # 6. 记录日志
        log_entry = {
            "state": current_state,
            "action": state_cfg.get("action"),
            "input": message,
            "output": result.get("reply", "")[:200],
            "next": wf_state.get("current_state"),
        }
        wf_state.setdefault("log", []).append(log_entry)

        # 7. 添加 AI 回复到会话
        reply = result.get("reply", "")
        messages.append({"role": "ai", "content": reply})

        # 8. 保存会话
        metadata = {"workflow": wf_state}
        if persona_id:
            metadata["persona_id"] = persona_id
        self.memory.save_conversation(
            user_id=user_id,
            session_id=session_id,
            messages=messages,
            summary=message[:40] + "…" if len(message) > 40 else message,
            source="pro",
            metadata=metadata,
        )

        # 9. 确定响应类型
        action = state_cfg.get("action", "")
        response_type = "guide"
        skill_name = None

        if action == "call":
            response_type = "skill_output"
            skill_name = state_cfg.get("skill")
        elif action == "aggregate":
            response_type = "final_script"
            skill_name = "get_daren"
        elif action == "select":
            response_type = "guide"
            skill_name = "get_daren"

        # select 动作返回选项按钮
        next_actions = None
        if action == "select" and not result.get("advance"):
            next_actions = self._build_select_actions(state_cfg)

        return {
            "session_id": session_id,
            "type": response_type,
            "content": reply,
            "workflow_state": wf_state["current_state"],
            "skill_name": skill_name,
            "next_actions": next_actions,
        }

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
            "slots": {},
            "outputs": {},
            "log": [],
        }

    def _execute_state(
        self,
        state_cfg: dict[str, Any],
        wf_state: dict[str, Any],
        user_input: str,
        user_id: str,
    ) -> dict[str, Any]:
        """调用 Get达人 skill 执行当前状态动作。"""
        if self.orch is None:
            return {"reply": "服务未就绪", "advance": False}

        try:
            skill = self.orch._find_skill("get_daren")
            if skill is None:
                return {"reply": "❌ Get达人 skill 未注册", "advance": False}
        except Exception as e:
            return {"reply": f"❌ 查找 Get达人 skill 失败：{e}", "advance": False}

        try:
            result = skill.invoke(
                {
                    "workflow_step": state_cfg,
                    "slots": wf_state.get("slots", {}),
                    "outputs": wf_state.get("outputs", {}),
                    "user_input": user_input,
                    "conversation_history": wf_state.get("log", [])[-10:],
                    "user_id": user_id,
                }
            )
        except Exception as e:
            logger.error("Get达人执行失败: %s", e, exc_info=True)
            return {"reply": f"❌ 调度失败：{e}", "advance": False}

        # 解析 Get达人返回的 JSON
        parsed = self._parse_daren_result(result)

        # 更新 slots 和 outputs
        if parsed.get("slots_update"):
            wf_state.setdefault("slots", {}).update(parsed["slots_update"])
        if parsed.get("outputs_update"):
            wf_state.setdefault("outputs", {}).update(parsed["outputs_update"])

        return parsed

    def _parse_daren_result(self, result: Any) -> dict[str, Any]:
        """解析 Get达人 skill 返回的结果。"""
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
                }
            except json.JSONDecodeError:
                pass

        return {"reply": raw, "advance": False, "slots_update": {}, "outputs_update": {}}

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

    # 模型切换
    if request.model and state.orch:
        state.orch.set_model(request.model)

    result = engine.process(
        session_id=request.session_id,
        user_id=user_id,
        message=request.message,
        outline=request.outline,
        persona_id=request.persona_id,
        model=request.model,
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
