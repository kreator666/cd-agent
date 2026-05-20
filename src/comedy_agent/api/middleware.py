"""FastAPI 中间件 —— 限流保护与请求日志。

提供基于滑动窗口的速率限制中间件，以及基础请求日志记录。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from comedy_agent.core.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# RateLimitMiddleware
# ------------------------------------------------------------------ #


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件。

    对写操作（POST / PUT / PATCH / DELETE）进行限流，读操作（GET）通常不限流，
    但可通过配置对高频读接口也启用限流。
    """

    def __init__(
        self,
        app: Any,
        limiter: RateLimiter,
        write_max: int = 60,
        write_window: int = 60,
        read_max: int = 120,
        read_window: int = 60,
    ) -> None:
        """初始化中间件。

        Args:
            app: FastAPI 应用实例。
            limiter: 限流器实例。
            write_max: 写操作窗口内最大请求数。
            write_window: 写操作窗口大小（秒）。
            read_max: 读操作窗口内最大请求数。
            read_window: 读操作窗口大小（秒）。
        """
        super().__init__(app)
        self.limiter = limiter
        self.write_max = write_max
        self.write_window = write_window
        self.read_max = read_max
        self.read_window = read_window

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """处理每个请求，检查是否超出限流阈值。"""
        method = request.method
        path = request.url.path
        client_host = request.client.host if request.client else "unknown"

        # 构造限流键：IP + 方法 + 路径前缀
        key = f"rate_limit:{client_host}:{method}:{path}"

        if method in ("POST", "PUT", "PATCH", "DELETE"):
            allowed = self.limiter.is_allowed(
                key, self.write_max, self.write_window
            )
            if not allowed:
                logger.warning("限流触发: %s %s from %s", method, path, client_host)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后再试"},
                )
        elif method == "GET":
            # 对 GET 也进行宽松限流（防止爬虫/刷接口）
            allowed = self.limiter.is_allowed(
                key, self.read_max, self.read_window
            )
            if not allowed:
                logger.warning("GET 限流触发: %s from %s", path, client_host)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后再试"},
                )

        # 记录请求耗时
        start = time.time()
        response = await call_next(request)
        elapsed = time.time() - start
        logger.debug("%s %s — %d (%.3fs)", method, path, response.status_code, elapsed)
        return response
