"""极速版路由 —— 趣味表达引擎。

提供一键加梗、IP 角色风格化、Token 预估等能力。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.memory.models import IPStyleData

router = APIRouter(tags=["speed"])

INTENSITY_COST = {"light": 10, "medium": 20, "heavy": 30}


class SpeedPolishRequest(BaseModel):
    """极速版趣味加工请求。"""

    text: str = Field(description="原始文本")
    intensity: str = Field(default="medium", description="加梗强度：light / medium / heavy")
    ip_role_id: str | None = Field(default=None, description="可选的 IP 角色 ID")
    project_id: str | None = Field(default=None, description="关联项目 ID")
    model: str | None = Field(default=None, description="使用的模型名称")


class IPRoleInfo(BaseModel):
    """极速版响应中返回的 IP 角色信息。"""

    role_id: str | None = Field(default=None, description="角色 ID")
    actor_name: str | None = Field(default=None, description="角色名称")
    avatar_url: str | None = Field(default=None, description="头像 URL")
    profile_url: str | None = Field(default=None, description="主页链接")


class SpeedPolishResponse(BaseModel):
    """极速版趣味加工响应。"""

    original: str = Field(description="原始文本")
    polished: str = Field(description="加梗后文本")
    ip_role: IPRoleInfo | None = Field(default=None, description="使用的 IP 角色信息")
    token_cost: int = Field(description="实际消耗 Token 数")
    estimated_tokens: int = Field(description="预估 Token 数")


class SpeedEstimateRequest(BaseModel):
    """Token 预估请求。"""

    text: str = Field(description="原始文本")
    intensity: str = Field(default="medium", description="加梗强度")


class SpeedEstimateResponse(BaseModel):
    """Token 预估响应。"""

    estimated_tokens: int = Field(description="预估 Token 数")
    estimated_cost: float = Field(description="预估费用（元）")


@router.post("/speed/polish", response_model=SpeedPolishResponse)
async def speed_polish(
    request: SpeedPolishRequest, user_id: str = Depends(get_current_user)
) -> SpeedPolishResponse:
    """极速版趣味加工：输入原始文本，返回加梗后的风格化文本。"""
    if state.orch is None:
        raise HTTPException(status_code=503, detail="服务未就绪")
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    cost = INTENSITY_COST.get(request.intensity, 20)
    account = state.memory.get_token_account(user_id)
    if account.balance < cost:
        raise HTTPException(
            status_code=402,
            detail=f"Token 余额不足（需 {cost}，余 {account.balance}）",
        )

    # 模型选择：用户传入 > 用户配置 > 默认
    model_name = request.model
    if not model_name:
        prefs = state.memory.list_preferences(user_id)
        for p in prefs:
            if p.key == "model_config" and p.value:
                model_name = p.value.get("speed_model")
                if model_name:
                    break
    if model_name:
        state.orch.set_model(model_name)

    # 加载 IP 角色风格片段（若指定）
    ip_role_info: IPRoleInfo | None = None
    ip_role_prompt: str | None = None
    if request.ip_role_id:
        role = state.memory.load_ip_style(request.ip_role_id)
        if role and role.status == "active":
            ip_role_prompt = role.prompt_snippet
            ip_role_info = IPRoleInfo(
                role_id=role.style_id,
                actor_name=role.actor_name,
                avatar_url=role.avatar_url,
                profile_url=role.profile_url,
            )
            # 更新使用次数
            role.usage_count = (role.usage_count or 0) + 1
            state.memory.save_ip_style(role)

    # 检索选中大V的知识库内容（若指定）
    ip_knowledge_lines: list[str] = []
    if request.ip_role_id:
        try:
            store = state.orch._get_user_vector_store(request.ip_role_id)
            docs = store.search(request.text, top_k=3)
            if docs:
                for idx, doc in enumerate(docs, 1):
                    source = doc.metadata.get("source", "大V知识库") if hasattr(doc, "metadata") and doc.metadata else "大V知识库"
                    text = doc.page_content.strip().replace("\n", " ") if hasattr(doc, "page_content") else str(doc)
                    ip_knowledge_lines.append(f"[{idx}] 来源: {source}\n{text}")
        except Exception:
            # 大V无知识库或检索失败，静默跳过
            pass

    # 构造 skill 指令调用 add_salt
    prompt = (
        f"使用 add_salt 技能 来对以下文本进行幽默润色。\n\n"
        f"原文：{request.text}\n"
        f"强度：{request.intensity}"
    )
    if ip_role_prompt:
        prompt += f"\n角色风格：{ip_role_prompt}"
    if ip_knowledge_lines:
        knowledge_text = "\n\n".join(ip_knowledge_lines)
        prompt += (
            f"\n\n【参考知识】\n"
            f"以下是与该文本相关的参考内容，请在润色时参考其中风格和表达方式：\n\n"
            f"{knowledge_text}\n"
            f"【参考知识结束】"
        )

    result = state.orch.run(prompt, user_id=user_id)
    polished = result.get("output", "")

    # Token 预估（简单字符数估算）
    estimated_tokens = int(len(request.text) * 0.8)

    state.memory.deduct_tokens(user_id, cost)
    session_id = uuid.uuid4().hex[:16]
    state.memory.save_conversation(
        user_id=user_id,
        session_id=session_id,
        messages=[
            {"role": "human", "content": request.text},
            {"role": "ai", "content": polished},
        ],
        summary=(request.text[:40] + "… [极速版]") if len(request.text) > 40 else (request.text + " [极速版]"),
        source="speed",
        metadata={
            "intensity": request.intensity,
            "original_text": request.text,
            "polished_text": polished,
            "token_cost": cost,
            "estimated_tokens": estimated_tokens,
            "ip_role_id": request.ip_role_id,
            "project_id": request.project_id,
        },
    )

    return SpeedPolishResponse(
        original=request.text,
        polished=polished,
        ip_role=ip_role_info,
        token_cost=cost,
        estimated_tokens=estimated_tokens,
    )


@router.get("/speed/ip-roles")
async def speed_ip_roles() -> list[dict[str, Any]]:
    """列出极速版可用的 IP 角色——从认证大V用户中按粉丝数取 top 10。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    users = state.memory.list_verified_users(limit=10)
    users.sort(key=lambda u: u["follower_count"], reverse=True)
    return [
        {
            "style_id": u["user_id"],
            "actor_name": u["nickname"] or u["user_id"],
            "avatar_url": u["avatar_url"],
            "follower_count": u["follower_count"],
        }
        for u in users
    ]


@router.get("/speed/history")
async def speed_history(user_id: str = Depends(get_current_user)) -> list[dict]:
    """获取当前用户的极速版生成历史。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")
    conversations = state.memory.list_conversations(user_id, limit=100)
    speed_convs = [c for c in conversations if c.source == "speed"]
    return [
        {
            "session_id": c.session_id,
            "original_text": c.metadata.get("original_text", "") if c.metadata else "",
            "polished_text": c.metadata.get("polished_text", "") if c.metadata else "",
            "intensity": c.metadata.get("intensity", "") if c.metadata else "",
            "token_cost": c.metadata.get("token_cost", 0) if c.metadata else 0,
            "ip_role_id": c.metadata.get("ip_role_id") if c.metadata else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in speed_convs
    ]


@router.post("/speed/estimate", response_model=SpeedEstimateResponse)
async def speed_estimate(request: SpeedEstimateRequest) -> SpeedEstimateResponse:
    """预估极速版 Token 消耗。"""
    estimated_tokens = int(len(request.text) * 0.8)
    # 简单定价：1 token = 0.0001 元（示例）
    estimated_cost = round(estimated_tokens * 0.0001, 4)
    return SpeedEstimateResponse(
        estimated_tokens=estimated_tokens,
        estimated_cost=estimated_cost,
    )
