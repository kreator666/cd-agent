"""认证安全工具 —— 密码哈希与 JWT Token。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)

# JWT 配置
SECRET_KEY = getattr(settings, "secret_key", None) or "comedy-agent-dev-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希值是否匹配。"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: str) -> str:
    """生成 JWT access token。

    Args:
        user_id: 用户唯一标识。

    Returns:
        JWT token 字符串。
    """
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    """解码并验证 JWT token，返回 user_id。

    Args:
        token: JWT token 字符串。

    Returns:
        user_id

    Raises:
        jwt.ExpiredSignatureError: token 已过期。
        jwt.InvalidTokenError: token 无效。
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    user_id: str = payload.get("sub")
    if user_id is None:
        raise jwt.InvalidTokenError("Token 缺少 sub 字段")
    return user_id
