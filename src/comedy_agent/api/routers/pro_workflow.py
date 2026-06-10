"""专业版 Wizard 工作流引擎 —— 对话式分步生成。

把一次性串行 Pipeline 改造为渐进式 Wizard 交互，每步引导用户选择或调用 Skill，
在聊天中展示中间结果，最终生成剧本。
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

_DEFAULT_WORKFLOW: list[dict[str, Any]] = [
    {
        "id": "outline_check",
        "type": "validation",
        "field": "outline",
        "message": "📋 请先设置选题大纲。请描述你想要创作的核心内容，例如：实习生被领导刁难后逆袭的职场段子。",
    },
    {
        "id": "genre_select",
        "type": "selection",
        "skill_type": "genre",
        "message": "🎭 请选择剧本体裁，这将决定整体的创作风格。",
    },
    {
        "id": "step_topic",
        "type": "skill",
        "skill": "topic",
        "message": "🔍 正在调用话题专家扩写话题背景与冲突点...",
        "requires_selection": True,
        "selection_skill_type": "topic",
    },
    {
        "id": "step_attitude",
        "type": "skill",
        "skill": "attitude",
        "message": "🎯 正在调用态度专家注入态度...",
        "requires_selection": True,
        "selection_skill_type": "attitude",
    },
    {
        "id": "step_emotion",
        "type": "skill",
        "skill": "emotion",
        "message": "💫 正在调用情绪专家调整情绪节奏...",
        "requires_selection": True,
        "selection_skill_type": "emotion",
    },
    {
        "id": "step_rule_persona",
        "type": "skill",
        "skill": "rule_persona",
        "message": "🎭 正在应用人物画像规则...",
        "requires_selection": False,
    },
    {
        "id": "step_composer",
        "type": "skill",
        "skill": "script_composer",
        "message": "📝 正在调用剧本编排专家生成最终剧本...",
        "is_final": True,
    },
]


def _load_workflow() -> list[dict[str, Any]]:
    """从 JSON 文件加载工作流配置，不存在则写入默认配置。"""
    if _WORKFLOW_FILE.exists():
        try:
            with _WORKFLOW_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception as e:
            logger.warning("工作流配置文件读取失败，使用默认配置: %s", e)
    # 写入默认配置
    try:
        _WORKFLOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _WORKFLOW_FILE.open("w", encoding="utf-8") as f:
            json.dump(_DEFAULT_WORKFLOW, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("工作流配置文件写入失败: %s", e)
    return list(_DEFAULT_WORKFLOW)


def _save_workflow(steps: list[dict[str, Any]]) -> None:
    """保存工作流配置到 JSON 文件。"""
    try:
        _WORKFLOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _WORKFLOW_FILE.open("w", encoding="utf-8") as f:
            json.dump(steps, f, ensure_ascii=False, indent=2)
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
    outline: str | None = Field(default=None, description="选题大纲")
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
# 工作流引擎
# ------------------------------------------------------------------ #
class ProWorkflowEngine:
    """专业版 Wizard 工作流引擎。

    维护工作流状态，根据当前步骤和用户输入决定下一步操作。
    状态持久化在 Conversation.extra_metadata 中。
    """

    def __init__(self, orch: Any, memory: Any, workflow_steps: list[dict[str, Any]] | None = None) -> None:
        self.orch = orch
        self.memory = memory
        self.workflow_steps = workflow_steps or list(_DEFAULT_WORKFLOW)

    # ------------------------------------------------------------------ #
    # 公共入口
    # ------------------------------------------------------------------ #
    def process(
        self,
        session_id: str | None,
        user_id: str,
        message: str,
        outline: str | None,
        persona_id: str | None,
        model: str | None,
    ) -> dict[str, Any]:
        """处理用户消息，推进工作流，返回响应。"""
        # 1. 加载或创建会话
        conv = None
        if session_id:
            conv = self.memory.load_conversation(user_id, session_id)

        if conv is None:
            session_id = uuid.uuid4().hex[:16]
            wf_state = self._init_state(outline, persona_id, model)
            messages: list[dict[str, Any]] = []
        else:
            session_id = conv.session_id
            wf_state = (conv.metadata or {}).get("workflow", {}) if conv.metadata else {}
            if not wf_state:
                wf_state = self._init_state(outline, persona_id, model)
            messages = list(conv.messages) if conv.messages else []

        # 2. 解析用户意图（设置大纲 / 选择 skill / 普通消息）
        self._parse_user_intent(message, wf_state)

        # 3. 添加用户消息到会话
        messages.append({"role": "human", "content": message})

        # 4. 执行当前步骤
        current_step_id = wf_state.get("current_step", "outline_check")
        step = self._find_step(current_step_id)
        result = self._execute_step(step, wf_state, user_id)

        # 5. 推进状态
        if result.get("advance", False):
            next_step = self._get_next_step(current_step_id)
            wf_state["current_step"] = next_step["id"] if next_step else "done"
            completed = wf_state.setdefault("completed_steps", [])
            if step["id"] not in completed:
                completed.append(step["id"])

        # 6. 添加 AI 回复到会话
        messages.append({"role": "ai", "content": result["content"]})

        # 7. 保存会话
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

        # 8. 返回
        return {
            "session_id": session_id,
            "type": result["type"],
            "content": result["content"],
            "workflow_state": wf_state["current_step"],
            "skill_name": result.get("skill_name"),
            "next_actions": result.get("next_actions"),
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
            "workflow_state": wf_state.get("current_step", "outline_check"),
            "metadata": conv.metadata,
        }

    # ------------------------------------------------------------------ #
    # 状态管理
    # ------------------------------------------------------------------ #
    @staticmethod
    def _init_state(
        outline: str | None,
        persona_id: str | None,
        model: str | None,
    ) -> dict[str, Any]:
        return {
            "current_step": "outline_check",
            "completed_steps": [],
            "outline": outline or "",
            "persona_id": persona_id or "",
            "model": model or "",
            "selected_skills": {},
            "intermediate_outputs": {},
            "current_text": outline or "",
        }

    def _parse_user_intent(self, message: str, state: dict[str, Any]) -> None:
        """从用户消息中提取设置/选择意图，更新状态。"""
        msg = message.strip()

        # 设置大纲：支持多种格式
        if msg.startswith("大纲：") or msg.startswith("大纲:"):
            state["outline"] = msg.split("：", 1)[1] if "：" in msg else msg.split(":", 1)[1]
            state["current_text"] = state["outline"]
        elif msg.startswith("设置大纲 "):
            state["outline"] = msg[len("设置大纲 "):]
            state["current_text"] = state["outline"]
        elif msg.lower().startswith("outline:"):
            state["outline"] = msg.split(":", 1)[1].strip()
            state["current_text"] = state["outline"]
        elif msg.lower().startswith("set outline "):
            state["outline"] = msg[len("set outline "):]
            state["current_text"] = state["outline"]

        # 选择 skill：解析 "@xxx" 或直接的 skill 名
        import re
        mention = re.search(r"@(\S+)", msg)
        if mention:
            selected_name = mention.group(1)
            current_step = state.get("current_step", "")
            step = self._find_step(current_step)
            if step and step.get("type") == "selection":
                skill_type = step.get("skill_type")
                if skill_type:
                    state.setdefault("selected_skills", {})[skill_type] = selected_name
            elif step and step.get("requires_selection"):
                sel_type = step.get("selection_skill_type")
                if sel_type:
                    state.setdefault("selected_skills", {})[sel_type] = selected_name
            return

        # 在 selection 步骤中，如果用户直接发送 skill 名（不是 @ 格式），也视为选择
        current_step_id = state.get("current_step", "")
        step = self._find_step(current_step_id)
        if step and step.get("type") == "selection":
            skill_type = step.get("skill_type")
            skills = self._list_skills_by_type(skill_type)
            for s in skills:
                if s["name"].lower() in msg.lower():
                    state.setdefault("selected_skills", {})[skill_type] = s["name"]
                    return
        elif step and step.get("requires_selection"):
            sel_type = step.get("selection_skill_type")
            skills = self._list_skills_by_type(sel_type)
            for s in skills:
                if s["name"].lower() in msg.lower():
                    state.setdefault("selected_skills", {})[sel_type] = s["name"]
                    return

    # ------------------------------------------------------------------ #
    # 步骤执行
    # ------------------------------------------------------------------ #
    def _execute_step(
        self, step: dict[str, Any], state: dict[str, Any], user_id: str
    ) -> dict[str, Any]:
        step_type = step["type"]

        if step_type == "validation":
            return self._exec_validation(step, state)

        if step_type == "selection":
            return self._exec_selection(step, state)

        if step_type == "skill":
            return self._exec_skill(step, state, user_id)

        return {"type": "guide", "content": "未知步骤类型", "advance": True}

    def _exec_validation(
        self, step: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        field = step.get("field", "outline")
        value = state.get(field, "")
        if not value or not str(value).strip():
            return {
                "type": "guide",
                "content": step["message"],
                "advance": False,
                "next_actions": [
                    {"action": f"set_{field}", "label": f"设置{field}", "hint": f"直接输入：{field}：你的内容"}
                ],
            }
        return {
            "type": "guide",
            "content": f"✅ {field}已确认：{value[:60]}{'...' if len(str(value)) > 60 else ''}",
            "advance": True,
        }

    def _exec_selection(
        self, step: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        skill_type = step.get("skill_type")
        selected = state.setdefault("selected_skills", {}).get(skill_type)

        if selected:
            return {
                "type": "guide",
                "content": f"✅ 已选择 {skill_type}：{selected}",
                "advance": True,
            }

        # 列出可选 skills
        skills = self._list_skills_by_type(skill_type)
        actions = [
            {"action": "select_skill", "label": s.get("name", ""), "value": s.get("name", "")}
            for s in skills
        ]
        return {
            "type": "guide",
            "content": step["message"],
            "advance": False,
            "next_actions": actions,
        }

    def _exec_skill(
        self, step: dict[str, Any], state: dict[str, Any], user_id: str
    ) -> dict[str, Any]:
        skill_name = step["skill"]

        # 如果需要选择但还没选，先引导选择
        if step.get("requires_selection"):
            sel_type = step.get("selection_skill_type")
            selected = state.setdefault("selected_skills", {}).get(sel_type)
            if not selected:
                skills = self._list_skills_by_type(sel_type)
                return {
                    "type": "guide",
                    "content": f"请先选择一位{sel_type}专家：",
                    "advance": False,
                    "next_actions": [
                        {"action": "select_skill", "label": s.get("name", ""), "value": s.get("name", "")}
                        for s in skills
                    ],
                }

        # 构建 prompt
        current_text = state.get("current_text", state.get("outline", ""))
        outline = state.get("outline", "")
        persona_id = state.get("persona_id", "")

        if skill_name == "rule_persona":
            # 需要注入人物画像规则
            persona = self.memory.load_persona(persona_id) if persona_id else None
            rule_content = persona.rule_content if persona else {}
            prompt = (
                f"使用 rule_persona 技能。\n"
                f"大纲：{current_text}\n"
                f"规则：{rule_content}"
            )
        elif skill_name == "script_composer":
            # 最终编排：传入原始大纲 + 所有中间结果
            context_parts = []
            for key, val in state.get("intermediate_outputs", {}).items():
                context_parts.append(f"【{key} 输出】\n{val}")
            context_text = "\n\n".join(context_parts)
            prompt = (
                f"使用 script_composer 技能。\n"
                f"大纲：{outline}\n"
                f"上下文：{context_text}"
            )
        else:
            prompt = f"使用 {skill_name} 技能。\n文本：{current_text}"

        # 调用模型
        try:
            result = self.orch.run(prompt, user_id=user_id)
            output = result.get("output", "")
        except Exception as e:
            logger.error("Skill %s 调用失败: %s", skill_name, e, exc_info=True)
            return {
                "type": "error",
                "content": f"❌ {skill_name} 调用失败：{e}",
                "advance": False,
                "skill_name": skill_name,
            }

        # 保存中间输出
        state.setdefault("intermediate_outputs", {})[skill_name] = output
        state["current_text"] = output

        if step.get("is_final"):
            return {
                "type": "final_script",
                "content": output,
                "advance": True,
                "skill_name": skill_name,
            }
        return {
            "type": "skill_output",
            "content": output,
            "advance": True,
            "skill_name": skill_name,
        }

    # ------------------------------------------------------------------ #
    # 辅助方法
    # ------------------------------------------------------------------ #
    def _find_step(self, step_id: str) -> dict[str, Any]:
        for s in self.workflow_steps:
            if s["id"] == step_id:
                return s
        return self.workflow_steps[0]

    def _get_next_step(self, current_id: str) -> dict[str, Any] | None:
        for i, s in enumerate(self.workflow_steps):
            if s["id"] == current_id and i + 1 < len(self.workflow_steps):
                return self.workflow_steps[i + 1]
        return None

    def _list_skills_by_type(self, skill_type: str | None) -> list[dict[str, Any]]:
        """列出指定类型的可用 skills。"""
        if self.orch is None or skill_type is None:
            return []
        skills = self.orch.list_skills()
        result = []
        for s in skills:
            info = {"name": s.get("name", ""), "description": s.get("description", "")}
            name = info["name"]
            inferred_type = "other"
            if "topic" in name:
                inferred_type = "topic"
            elif "attitude" in name:
                inferred_type = "attitude"
            elif "emotion" in name:
                inferred_type = "emotion"
            elif "genre" in name:
                inferred_type = "genre"
            elif "rule_persona" in name:
                inferred_type = "rule_persona"
            elif "script_composer" in name:
                inferred_type = "script_composer"
            if inferred_type == skill_type:
                result.append(info)
        return result


# ------------------------------------------------------------------ #
# 全局引擎实例（lazy init）
# ------------------------------------------------------------------ #
_workflow_engine: ProWorkflowEngine | None = None


def _get_engine() -> ProWorkflowEngine:
    global _workflow_engine
    if _workflow_engine is None:
        if state.orch is None or state.memory is None:
            raise HTTPException(status_code=503, detail="服务未就绪")
        steps = _load_workflow()
        _workflow_engine = ProWorkflowEngine(orch=state.orch, memory=state.memory, workflow_steps=steps)
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

    接收用户消息，推进工作流，返回引导消息或 Skill 输出。
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
class WorkflowStep(BaseModel):
    """工作流步骤模型。"""

    id: str = Field(description="步骤唯一标识")
    type: str = Field(description="步骤类型：validation / selection / skill")
    message: str = Field(description="引导消息")
    field: str | None = Field(default=None, description="validation 类型对应的字段名")
    skill_type: str | None = Field(default=None, description="selection 类型对应的 skill 分类")
    skill: str | None = Field(default=None, description="skill 类型调用的 skill 名称")
    requires_selection: bool | None = Field(default=None, description="skill 步骤是否需要先选择")
    selection_skill_type: str | None = Field(default=None, description="需要选择时的 skill 分类")
    is_final: bool | None = Field(default=None, description="是否为最终步骤")


class WorkflowConfigResponse(BaseModel):
    """工作流配置响应。"""

    steps: list[WorkflowStep] = Field(description="工作流步骤列表")


@router.get("/admin/workflow", response_model=WorkflowConfigResponse)
async def admin_get_workflow(
    _admin: str = Depends(require_admin),
) -> WorkflowConfigResponse:
    """获取当前专业版工作流配置（仅管理员）。"""
    steps = _load_workflow()
    return WorkflowConfigResponse(steps=[WorkflowStep(**s) for s in steps])


@router.put("/admin/workflow")
async def admin_update_workflow(
    request: WorkflowConfigResponse,
    _admin: str = Depends(require_admin),
) -> dict[str, bool]:
    """更新专业版工作流配置（仅管理员）。"""
    steps = []
    for i, s in enumerate(request.steps):
        step = s.model_dump(exclude_none=True)
        if not step.get("id"):
            raise HTTPException(status_code=400, detail=f"第 {i + 1} 步缺少 id")
        if step.get("type") not in {"validation", "selection", "skill"}:
            raise HTTPException(status_code=400, detail=f"第 {i + 1} 步 type 非法")
        steps.append(step)

    _save_workflow(steps)

    # 刷新引擎实例使新配置生效
    global _workflow_engine
    _workflow_engine = None

    return {"success": True}
