"""专业版路由 —— 人物画像、Skill 列表与参考文件上传。

为 `pro-b.html` 提供 `/pro/personas`、`/pro/skills`、`/pro/upload` 等支撑接口。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.core.config import settings
from comedy_agent.memory.models import PersonaData

router = APIRouter(tags=["pro"])


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

    可选类型：writing / other
    """
    result: list[dict] = []

    # 1. 旧版 ComedySkill 工具（分析/填槽类）
    if state.orch is not None:
        skills = state.orch.list_skills()
        for s in skills:
            info = {
                "id": s.get("name", ""),
                "name": s.get("name", ""),
                "description": s.get("description", ""),
                "type": getattr(s, "task_type", "unknown"),
            }
            # 尝试从 Skill 类名推断类型
            name = info["name"]
            if "standup" in name or name in ("standup_generator", "generator"):
                info["skill_type"] = "writing"
            else:
                info["skill_type"] = "other"
            if skill_type is None or info["skill_type"] == skill_type:
                result.append(info)

    # 2. 新版写作类 Skill（供 v4 Writer 使用）
    from comedy_agent.core.skill_loader import load_skill_configs

    for cfg in load_skill_configs(settings.skills_dir):
        if cfg.metadata.get("kind") != "standup":
            continue
        info = {
            "id": cfg.id,
            "name": cfg.name,
            "description": cfg.description,
            "type": cfg.task_type,
            "skill_type": "writing",
        }
        if skill_type is None or skill_type == "writing":
            result.append(info)

    return result



