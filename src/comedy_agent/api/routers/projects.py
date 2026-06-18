"""项目路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.memory.models import ProjectData

router = APIRouter(tags=["projects"])


class ProjectCreateRequest(BaseModel):
    """创建项目请求。"""

    name: str = Field(description="项目名称")
    project_type: str | None = Field(default=None, description="项目类型")


class ProjectListResponse(BaseModel):
    """项目列表响应。"""

    projects: list[ProjectData] = Field(description="项目列表")


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(user_id: str = Depends(get_current_user)) -> ProjectListResponse:
    """列出当前用户的所有项目。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    return ProjectListResponse(projects=state.memory.list_projects(user_id))


@router.post("/projects", response_model=ProjectData)
async def create_project(
    request: ProjectCreateRequest, user_id: str = Depends(get_current_user)
) -> ProjectData:
    """创建新项目。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    project = ProjectData(user_id=user_id, name=request.name, project_type=request.project_type)
    return state.memory.save_project(user_id, project)


@router.get("/projects/{project_id}", response_model=ProjectData)
async def get_project(
    project_id: str, user_id: str = Depends(get_current_user)
) -> ProjectData:
    """获取项目详情。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    project = state.memory.load_project(user_id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.put("/projects/{project_id}", response_model=ProjectData)
async def update_project(
    project_id: str,
    request: ProjectCreateRequest,
    user_id: str = Depends(get_current_user),
) -> ProjectData:
    """更新项目。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    existing = state.memory.load_project(user_id, project_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    project = ProjectData(
        project_id=project_id,
        user_id=user_id,
        name=request.name,
        project_type=request.project_type,
    )
    return state.memory.save_project(user_id, project)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str, user_id: str = Depends(get_current_user)
) -> dict[str, bool]:
    """删除项目。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    ok = state.memory.delete_project(user_id, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"success": True}
