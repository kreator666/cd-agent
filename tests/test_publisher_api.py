"""测试一键发布相关 API。"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from comedy_agent.api.server import app
from comedy_agent.publisher.models import PlatformType, PublishResult


def _patched_create_engine(*args, **kwargs):
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


def _register_and_login(client: TestClient, user_id: str, password: str = "testpass"):
    client.post("/auth/register", json={"user_id": user_id, "password": password})
    resp = client.post("/auth/login", json={"user_id": user_id, "password": password})
    return resp.json()["access_token"]


@pytest.fixture
def client():
    """提供已认证的 TestClient，memory 使用内存数据库。"""
    with patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ), patch(
        "comedy_agent.api.server.AgentOrchestrator"
    ) as mock_orch_cls, patch(
        "comedy_agent.auth.router.SQLMemoryStore"
    ) as mock_auth_store_cls, patch(
        "comedy_agent.api.middleware.RateLimitMiddleware.dispatch",
        new=lambda self, request, call_next: call_next(request),
    ):
        mock_orch = MagicMock()
        mock_orch.run.return_value = {"output": "测试", "messages": []}
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore

        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store

        with TestClient(app) as c:
            yield c


@pytest.fixture
def auth_token(client):
    return _register_and_login(client, "pub_test_user")


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def sample_video(tmp_path):
    """创建一个临时视频文件用于测试上传。"""
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake video content")
    return video_path


class TestPublishUpload:
    """测试视频上传接口。"""

    def test_upload_video_success(self, client, auth_headers, sample_video):
        with open(sample_video, "rb") as f:
            resp = client.post(
                "/publish/upload",
                headers=auth_headers,
                files={"file": ("sample.mp4", f, "video/mp4")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["filename"] == "sample.mp4"
        assert data["video_path"].endswith("sample.mp4")
        assert Path(data["video_path"]).exists()

    def test_upload_unauthorized(self, client, sample_video):
        with open(sample_video, "rb") as f:
            resp = client.post(
                "/publish/upload",
                files={"file": ("sample.mp4", f, "video/mp4")},
            )
        assert resp.status_code == 401

    def test_upload_invalid_extension(self, client, auth_headers, tmp_path):
        bad_file = tmp_path / "sample.txt"
        bad_file.write_text("not a video")
        with open(bad_file, "rb") as f:
            resp = client.post(
                "/publish/upload",
                headers=auth_headers,
                files={"file": ("sample.txt", f, "text/plain")},
            )
        assert resp.status_code == 400


class TestPublishLoginStatus:
    """测试登录状态检查接口。"""

    def test_login_status_bilibili_not_logged_in(self, client, auth_headers):
        with patch(
            "comedy_agent.api.routers.publish.BilibiliAdapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.platform_type = PlatformType.BILIBILI
            mock_adapter.platform_name = "B站"
            mock_adapter.check_login_status = AsyncMock(return_value=False)
            mock_adapter.cleanup = AsyncMock(return_value=None)
            mock_adapter_cls.return_value = mock_adapter

            resp = client.get("/publish/login-status", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["platform"] == "bilibili"
            assert data[0]["name"] == "BILIBILI"
            assert data[0]["logged_in"] is False


class TestPublish:
    """测试一键发布接口。"""

    def test_publish_bilibili_not_logged_in(self, client, auth_headers, sample_video):
        with patch(
            "comedy_agent.api.routers.publish.BilibiliAdapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.platform_type = PlatformType.BILIBILI
            mock_adapter.platform_name = "B站"
            mock_adapter.pre_publish_check = AsyncMock(return_value=(True, ""))
            mock_adapter.publish = AsyncMock(
                return_value=PublishResult(
                    platform=PlatformType.BILIBILI,
                    success=False,
                    message="登录失败，无法发布",
                )
            )
            mock_adapter.cleanup = AsyncMock(return_value=None)
            mock_adapter_cls.return_value = mock_adapter

            resp = client.post(
                "/publish/",
                headers=auth_headers,
                json={
                    "title": "测试标题",
                    "content": "测试描述",
                    "tags": "测试, B站",
                    "video_path": str(sample_video),
                    "platforms": ["bilibili"],
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False
            assert len(data["results"]) == 1
            assert data["results"][0]["platform"] == "bilibili"
            assert data["results"][0]["success"] is False
            assert "登录" in data["results"][0]["message"]

    def test_publish_bilibili_success(self, client, auth_headers, sample_video):
        with patch(
            "comedy_agent.api.routers.publish.BilibiliAdapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.platform_type = PlatformType.BILIBILI
            mock_adapter.platform_name = "B站"
            mock_adapter.pre_publish_check = AsyncMock(return_value=(True, ""))
            mock_adapter.publish = AsyncMock(
                return_value=PublishResult(
                    platform=PlatformType.BILIBILI,
                    success=True,
                    message="视频投稿成功",
                    url="https://www.bilibili.com/video/BV1234567890",
                    content_id="BV1234567890",
                )
            )
            mock_adapter.cleanup = AsyncMock(return_value=None)
            mock_adapter_cls.return_value = mock_adapter

            resp = client.post(
                "/publish/",
                headers=auth_headers,
                json={
                    "title": "测试标题",
                    "content": "测试描述",
                    "tags": "测试, B站",
                    "video_path": str(sample_video),
                    "platforms": ["bilibili"],
                    "category": "知识",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert len(data["results"]) == 1
            assert data["results"][0]["success"] is True
            assert data["results"][0]["url"].startswith("https://www.bilibili.com")

    def test_publish_missing_title(self, client, auth_headers, sample_video):
        resp = client.post(
            "/publish/",
            headers=auth_headers,
            json={
                "title": "",
                "content": "测试描述",
                "video_path": str(sample_video),
                "platforms": ["bilibili"],
            },
        )
        assert resp.status_code == 400

    def test_publish_missing_video_path(self, client, auth_headers):
        resp = client.post(
            "/publish/",
            headers=auth_headers,
            json={
                "title": "测试标题",
                "content": "测试描述",
                "video_path": "",
                "platforms": ["bilibili"],
            },
        )
        assert resp.status_code == 400

    def test_publish_video_not_found(self, client, auth_headers):
        resp = client.post(
            "/publish/",
            headers=auth_headers,
            json={
                "title": "测试标题",
                "content": "测试描述",
                "video_path": "/not/exist/video.mp4",
                "platforms": ["bilibili"],
            },
        )
        assert resp.status_code == 400


class TestBilibiliLogin:
    """测试 B站 登录相关接口。"""

    def test_login_qrcode_success(self, client, auth_headers):
        with patch(
            "comedy_agent.api.routers.publish.BilibiliAdapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.platform_type = PlatformType.BILIBILI
            mock_adapter.platform_name = "B站"
            mock_adapter.login_with_qrcode = MagicMock(
                return_value=("test_auth_code", "https://test.qrcode.url", "data:image/png;base64,abc")
            )
            mock_adapter.verify_qrcode_login = MagicMock(return_value=True)
            mock_adapter.cleanup = AsyncMock(return_value=None)
            mock_adapter_cls.return_value = mock_adapter

            resp = client.post(
                "/publish/bilibili/login-qrcode",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["auth_code"] == "test_auth_code"
            assert data["qrcode_url"] == "https://test.qrcode.url"
            assert data["qrcode_image"].startswith("data:image/png;base64,")
            mock_adapter.verify_qrcode_login.assert_called_once_with("test_auth_code")

    def test_login_poll(self, client, auth_headers):
        with patch(
            "comedy_agent.api.routers.publish.BilibiliAdapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.platform_type = PlatformType.BILIBILI
            mock_adapter.platform_name = "B站"
            mock_adapter.check_login_status = AsyncMock(return_value=True)
            mock_adapter.cleanup = AsyncMock(return_value=None)
            mock_adapter_cls.return_value = mock_adapter

            resp = client.get(
                "/publish/bilibili/login-poll/test_auth_code",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["logged_in"] is True

    def test_login_cookie_success(self, client, auth_headers, tmp_path):
        cookie_path = tmp_path / "cookie.json"
        cookie_path.write_text('{"test": "cookie"}')

        with patch(
            "comedy_agent.api.routers.publish.BilibiliAdapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.platform_type = PlatformType.BILIBILI
            mock_adapter.platform_name = "B站"
            mock_adapter.login_with_cookie_file = MagicMock(return_value=True)
            mock_adapter.cleanup = AsyncMock(return_value=None)
            mock_adapter_cls.return_value = mock_adapter

            with open(cookie_path, "rb") as f:
                resp = client.post(
                    "/publish/bilibili/login-cookie",
                    headers=auth_headers,
                    files={"file": ("cookie.json", f, "application/json")},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "成功" in data["message"]

    def test_login_cookie_invalid_extension(self, client, auth_headers, tmp_path):
        bad_path = tmp_path / "cookie.txt"
        bad_path.write_text("not json")

        with open(bad_path, "rb") as f:
            resp = client.post(
                "/publish/bilibili/login-cookie",
                headers=auth_headers,
                files={"file": ("cookie.txt", f, "text/plain")},
            )
        assert resp.status_code == 400

    def test_login_cookie_failure(self, client, auth_headers, tmp_path):
        cookie_path = tmp_path / "cookie.json"
        cookie_path.write_text('{"test": "cookie"}')

        with patch(
            "comedy_agent.api.routers.publish.BilibiliAdapter"
        ) as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.platform_type = PlatformType.BILIBILI
            mock_adapter.platform_name = "B站"
            mock_adapter.login_with_cookie_file = MagicMock(return_value=False)
            mock_adapter.cleanup = AsyncMock(return_value=None)
            mock_adapter_cls.return_value = mock_adapter

            with open(cookie_path, "rb") as f:
                resp = client.post(
                    "/publish/bilibili/login-cookie",
                    headers=auth_headers,
                    files={"file": ("cookie.json", f, "application/json")},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False
            assert "失败" in data["message"]
