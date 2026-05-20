"""测试 API 限流中间件。"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from comedy_agent.api.middleware import RateLimitMiddleware


@pytest.fixture
def mock_limiter():
    """返回可控的限流器 mock。"""
    limiter = MagicMock()
    limiter.is_allowed.return_value = True
    return limiter


@pytest.fixture
def client(mock_limiter):
    """提供带限流中间件的 TestClient。"""
    app = FastAPI()

    @app.get("/read")
    async def read():
        return {"ok": True}

    @app.post("/write")
    async def write():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        limiter=mock_limiter,
        write_max=10,
        write_window=60,
        read_max=20,
        read_window=60,
    )

    with TestClient(app) as c:
        yield c


class TestRateLimitMiddleware:
    """限流中间件测试。"""

    def test_read_request_allowed(self, client, mock_limiter):
        response = client.get("/read")
        assert response.status_code == 200
        mock_limiter.is_allowed.assert_called_once()
        call_args = mock_limiter.is_allowed.call_args[0]
        assert "GET" in call_args[0]
        assert "/read" in call_args[0]
        assert call_args[1] == 20  # read_max

    def test_write_request_allowed(self, client, mock_limiter):
        mock_limiter.is_allowed.return_value = True
        response = client.post("/write")
        assert response.status_code == 200
        call_args = mock_limiter.is_allowed.call_args[0]
        assert "POST" in call_args[0]
        assert "/write" in call_args[0]
        assert call_args[1] == 10  # write_max

    def test_read_request_blocked(self, client, mock_limiter):
        mock_limiter.is_allowed.return_value = False
        response = client.get("/read")
        assert response.status_code == 429
        assert "请求过于频繁" in response.json()["detail"]

    def test_write_request_blocked(self, client, mock_limiter):
        mock_limiter.is_allowed.return_value = False
        response = client.post("/write")
        assert response.status_code == 429
        assert "请求过于频繁" in response.json()["detail"]

    def test_limiter_not_called_for_options(self, mock_limiter):
        app = FastAPI()

        @app.options("/cors")
        async def cors():
            return {"ok": True}

        app.add_middleware(
            RateLimitMiddleware,
            limiter=mock_limiter,
        )

        with TestClient(app) as c:
            response = c.options("/cors")
            assert response.status_code == 200
            # OPTIONS 不在限流范围内
            mock_limiter.is_allowed.assert_not_called()
