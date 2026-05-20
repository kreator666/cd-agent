"""FastAPI 认证依赖。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from comedy_agent.auth.security import decode_access_token

# OAuth2 密码流（实际我们用自定义登录接口，这里仅用于 Swagger/UI 自动文档生成）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(token: Annotated[str | None, Depends(oauth2_scheme)]) -> str:
    """从 Authorization header 提取并验证 JWT token，返回 user_id。

    用于保护需要登录的路由。

    Args:
        token: Bearer token。

    Returns:
        用户唯一标识 user_id。

    Raises:
        HTTPException(401): token 缺失或无效。
    """
    if not token:
        raise HTTPException(status_code=401, detail="未提供认证凭证", headers={"WWW-Authenticate": "Bearer"})

    try:
        user_id = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="认证凭证无效或已过期", headers={"WWW-Authenticate": "Bearer"})

    return user_id
