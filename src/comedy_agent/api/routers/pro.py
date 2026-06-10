"""专业版路由 —— 剧本工坊。

提供人物画像管理、Skill 组合、结构化剧本生成等能力。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.core.config import settings
from comedy_agent.memory.models import PersonaData

router = APIRouter(tags=["pro"])

# Skill 类型到预估消耗的映射（简化模型）
SKILL_COST = {
    "topic": 15,
    "attitude": 10,
    "emotion": 10,
    "genre": 15,
    "rule_persona": 20,
    "script_composer": 25,
}


# ------------------------------------------------------------------ #
# 请求/响应模型
# ------------------------------------------------------------------ #
class PersonaCreateRequest(BaseModel):
    """创建人物画像请求。"""

    name: str = Field(description="画像名称")
    description: str | None = Field(default=None, description="画像描述")
    rule_content: dict = Field(default_factory=dict, description="结构化写作规则约束")
    skill_id: str | None = Field(default=None, description="关联的 rule 类型 Skill ID")
    reference_files: list[dict] | None = Field(default=None, description="参考文件列表")


class PersonaUpdateRequest(BaseModel):
    """更新人物画像请求。"""

    name: str | None = Field(default=None, description="画像名称")
    description: str | None = Field(default=None, description="画像描述")
    rule_content: dict | None = Field(default=None, description="结构化写作规则约束")
    skill_id: str | None = Field(default=None, description="关联的 rule 类型 Skill ID")
    reference_files: list[dict] | None = Field(default=None, description="参考文件列表")
    is_active: bool | None = Field(default=None, description="是否启用")


class ProGenerateRequest(BaseModel):
    """专业版剧本生成请求。"""

    outline: str = Field(description="创意大纲")
    persona_id: str = Field(description="人物画像 ID")
    skill_ids: list[str] = Field(default_factory=list, description="Skill 组合列表")
    project_id: str | None = Field(default=None, description="关联项目 ID")
    model: str | None = Field(default=None, description="使用的模型名称")
    confirm_budget: bool = Field(default=False, description="是否已确认预算告警")


class ProGenerateResponse(BaseModel):
    """专业版剧本生成响应。"""

    script: str = Field(description="生成的 Markdown 剧本")
    persona_name: str | None = Field(default=None, description="使用的人物画像名称")
    skills_used: list[str] = Field(default_factory=list, description="实际使用的 Skill 列表")
    token_cost: int = Field(description="实际消耗 Token 数")
    estimated_tokens: int = Field(description="预估 Token 数")


class ProEstimateRequest(BaseModel):
    """专业版 Token 预估请求。"""

    outline: str = Field(description="创意大纲")
    skill_ids: list[str] = Field(default_factory=list, description="Skill 组合列表")


class ProEstimateResponse(BaseModel):
    """专业版 Token 预估响应。"""

    estimated_tokens: int = Field(description="预估 Token 数")
    estimated_cost: float = Field(description="预估费用（元）")
    budget_warning: bool = Field(default=False, description="是否超出预算告警阈值")


# ------------------------------------------------------------------ #
# 人物画像 CRUD
# ------------------------------------------------------------------ #
@router.get("/pro/personas")
async def list_personas(user_id: str = Depends(get_current_user)) -> list[PersonaData]:
    """列出当前用户的人物画像。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    return state.memory.list_personas(creator_id=user_id)


@router.post("/pro/personas", response_model=PersonaData)
async def create_persona(
    request: PersonaCreateRequest, user_id: str = Depends(get_current_user)
) -> PersonaData:
    """创建人物画像。仅当前用户自用。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    persona = PersonaData(
        creator_id=user_id,
        name=request.name,
        description=request.description,
        rule_content=request.rule_content,
        skill_id=request.skill_id,
        reference_files=request.reference_files,
    )
    return state.memory.save_persona(persona)


@router.get("/pro/personas/{persona_id}")
async def get_persona(
    persona_id: str, user_id: str = Depends(get_current_user)
) -> PersonaData:
    """获取人物画像详情。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    persona = state.memory.load_persona(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="人物画像不存在")
    # 简单权限校验：只能查看自己的画像
    if persona.creator_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问该人物画像")
    return persona


@router.put("/pro/personas/{persona_id}")
async def update_persona(
    persona_id: str,
    request: PersonaUpdateRequest,
    user_id: str = Depends(get_current_user),
) -> PersonaData:
    """更新人物画像。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    existing = state.memory.load_persona(persona_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="人物画像不存在")
    if existing.creator_id != user_id:
        raise HTTPException(status_code=403, detail="无权修改该人物画像")
    if request.name is not None:
        existing.name = request.name
    if request.description is not None:
        existing.description = request.description
    if request.rule_content is not None:
        existing.rule_content = request.rule_content
    if request.skill_id is not None:
        existing.skill_id = request.skill_id
    if request.reference_files is not None:
        existing.reference_files = request.reference_files
    if request.is_active is not None:
        existing.is_active = request.is_active
    return state.memory.save_persona(existing)


@router.post("/pro/upload")
async def upload_reference_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
) -> dict[str, str]:
    """上传画像参考文件。文件保存在用户私有目录下，仅该用户可访问。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    upload_dir = Path(settings.data_dir) / "references" / user_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "unknown").name
    save_path = upload_dir / safe_name
    counter = 1
    original_save_path = save_path
    while save_path.exists():
        stem = original_save_path.stem
        suffix = original_save_path.suffix
        save_path = upload_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    content = await file.read()
    save_path.write_bytes(content)

    return {
        "filename": safe_name,
        "saved_name": save_path.name,
        "path": str(save_path),
        "size": str(len(content)),
    }


@router.delete("/pro/personas/{persona_id}")
async def delete_persona(
    persona_id: str, user_id: str = Depends(get_current_user)
) -> dict[str, bool]:
    """删除人物画像。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    existing = state.memory.load_persona(persona_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="人物画像不存在")
    if existing.creator_id != user_id:
        raise HTTPException(status_code=403, detail="无权删除该人物画像")
    ok = state.memory.delete_persona(persona_id)
    return {"success": ok}


# ------------------------------------------------------------------ #
# Skill 组合与生成
# ------------------------------------------------------------------ #
@router.get("/pro/skills")
async def list_pro_skills(skill_type: str | None = None) -> list[dict]:
    """列出专业版可用 Skill，支持按类型过滤。

    可选类型：topic / attitude / emotion / genre / rule_persona / script_composer / style_mimic
    """
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    skills = state.orch.list_skills()
    result = []
    for s in skills:
        info = {
            "name": s.get("name", ""),
            "description": s.get("description", ""),
            "type": getattr(s, "task_type", "unknown"),
        }
        # 尝试从 Skill 类名推断类型
        name = info["name"]
        if "topic" in name:
            info["skill_type"] = "topic"
        elif "attitude" in name:
            info["skill_type"] = "attitude"
        elif "emotion" in name:
            info["skill_type"] = "emotion"
        elif "genre" in name:
            info["skill_type"] = "genre"
        elif "rule_persona" in name:
            info["skill_type"] = "rule_persona"
        elif "script_composer" in name:
            info["skill_type"] = "script_composer"
        elif "style_mimic" in name:
            info["skill_type"] = "style_mimic"
        else:
            info["skill_type"] = "other"
        if skill_type is None or info["skill_type"] == skill_type:
            result.append(info)
    return result


@router.post("/pro/estimate", response_model=ProEstimateResponse)
async def pro_estimate(
    request: ProEstimateRequest, user_id: str = Depends(get_current_user)
) -> ProEstimateResponse:
    """预估专业版组合 Skill Token 消耗。"""
    # 基础消耗 + 各 Skill 消耗
    base_tokens = int(len(request.outline) * 0.8)
    skill_tokens = sum(SKILL_COST.get(sid, 10) for sid in request.skill_ids)
    estimated_tokens = base_tokens + skill_tokens
    estimated_cost = round(estimated_tokens * 0.0001, 4)

    # 预算告警：简化逻辑，若预估超过 1000 tokens 则告警
    budget_warning = estimated_tokens > 1000

    return ProEstimateResponse(
        estimated_tokens=estimated_tokens,
        estimated_cost=estimated_cost,
        budget_warning=budget_warning,
    )


@router.post("/pro/generate", response_model=ProGenerateResponse)
async def pro_generate(
    request: ProGenerateRequest, user_id: str = Depends(get_current_user)
) -> ProGenerateResponse:
    """专业版剧本生成：人物画像 + Skill 组合 → 结构化 Markdown 剧本。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    # 1. 校验人物画像
    persona = state.memory.load_persona(request.persona_id)
    if persona is None or not persona.is_active:
        raise HTTPException(
            status_code=400,
            detail="无可用的写作画像，请先创建人物画像后再生成剧本",
        )

    # 2. Token 预算检查
    base_tokens = int(len(request.outline) * 0.8)
    skill_tokens = sum(SKILL_COST.get(sid, 10) for sid in request.skill_ids)
    estimated_tokens = base_tokens + skill_tokens
    token_cost = estimated_tokens  # 简化：按预估扣费

    account = state.memory.get_token_account(user_id)
    if account.balance < token_cost:
        raise HTTPException(
            status_code=402,
            detail=f"Token 余额不足（需 {token_cost}，余 {account.balance}）",
        )

    # 预算告警
    if estimated_tokens > 1000 and not request.confirm_budget:
        raise HTTPException(
            status_code=402,
            detail="本次预计消耗超预算，是否继续？",
        )

    # 模型选择：用户传入 > 用户配置 > 默认
    model_name = request.model
    if not model_name:
        prefs = state.memory.list_preferences(user_id)
        for p in prefs:
            if p.key == "model_config" and p.value:
                model_name = p.value.get("pro_model")
                if model_name:
                    break
    if model_name:
        state.orch.set_model(model_name)

    # 3. 构造组合 Pipeline 调用
    # 按类型排序：topic → attitude → emotion → genre → rule_persona → script_composer
    type_order = ["topic", "attitude", "emotion", "genre", "rule_persona", "script_composer"]
    ordered_skills = []
    for t in type_order:
        for sid in request.skill_ids:
            if sid == t:
                ordered_skills.append(sid)
    # 补充未按类型排序的 skill
    for sid in request.skill_ids:
        if sid not in ordered_skills:
            ordered_skills.append(sid)

    # 构建上下文链
    context_parts: list[str] = []
    current_text = request.outline

    for skill_name in ordered_skills:
        if skill_name == "rule_persona":
            # 人物画像规则注入
            rule_text = (
                f"【人物画像规则】\n"
                f"画像名称：{persona.name}\n"
                f"规则约束：{persona.rule_content}\n"
            )
            context_parts.append(rule_text)
            prompt = (
                f"使用 rule_persona 技能。\n"
                f"大纲：{current_text}\n"
                f"规则：{persona.rule_content}"
            )
            result = state.orch.run(prompt, user_id=user_id)
            current_text = result.get("output", current_text)
            context_parts.append(f"【rule_persona 输出】\n{current_text}")
        elif skill_name == "script_composer":
            # 最终编排
            context_text = "\n\n".join(context_parts)
            prompt = (
                f"使用 script_composer 技能。\n"
                f"大纲：{request.outline}\n"
                f"上下文：{context_text}"
            )
            result = state.orch.run(prompt, user_id=user_id)
            current_text = result.get("output", current_text)
        else:
            # 通用 skill 调用
            prompt = (
                f"使用 {skill_name} 技能。\n"
                f"文本：{current_text}"
            )
            result = state.orch.run(prompt, user_id=user_id)
            current_text = result.get("output", current_text)
            context_parts.append(f"【{skill_name} 输出】\n{current_text}")

    # 如果没有 script_composer，current_text 就是最终结果
    script = current_text

    # 更新画像使用次数
    persona.usage_count = (persona.usage_count or 0) + 1
    state.memory.save_persona(persona)

    # 扣除 Token
    state.memory.deduct_tokens(user_id, token_cost)

    # 保存生成记录
    session_id = uuid.uuid4().hex[:16]
    state.memory.save_conversation(
        user_id=user_id,
        session_id=session_id,
        messages=[
            {"role": "human", "content": request.outline},
            {"role": "ai", "content": script},
        ],
        summary=(request.outline[:40] + "… [专业版]") if len(request.outline) > 40 else (request.outline + " [专业版]"),
        source="pro",
        metadata={
            "persona_id": request.persona_id,
            "persona_name": persona.name,
            "combined_skill_ids": ordered_skills,
            "token_cost": token_cost,
            "estimated_tokens": estimated_tokens,
            "project_id": request.project_id,
        },
    )

    return ProGenerateResponse(
        script=script,
        persona_name=persona.name,
        skills_used=ordered_skills,
        token_cost=token_cost,
        estimated_tokens=estimated_tokens,
    )
