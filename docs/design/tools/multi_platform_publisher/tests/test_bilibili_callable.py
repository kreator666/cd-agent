"""
测试 B站（bilibili）视频上传功能是否可调用。

说明：
- 该测试不执行真实投稿，避免污染账号。
- 仅验证 bilitool 依赖、API 可用性、登录状态以及未登录时上传接口的调用行为。
- bilitool 0.1.3 仅支持二维码 / cookie 文件登录，不支持账号密码登录。

运行方式：
    cd docs/design/tools/multi_platform_publisher
    pip install -r requirements.txt
    pytest tests/test_bilibili_callable.py -v
    # 或直接执行
    python tests/test_bilibili_callable.py
"""

import importlib.metadata
import io
import os
import sys
import tempfile
from pathlib import Path

import dotenv
import pytest

# 修复 Windows bash 下中文输出乱码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


def load_env_example():
    """加载 .env.example 中的 bilibili 凭据。"""
    env_path = ROOT / ".env.example"
    if not env_path.exists():
        return None, None
    dotenv.load_dotenv(env_path)
    return os.getenv("BILIBILI_USERNAME", "").strip(), os.getenv("BILIBILI_PASSWORD", "").strip()


def test_bilitool_imported():
    """bilitool 依赖可正常导入。"""
    import bilitool
    from bilitool import LoginController, UploadController, FeedController

    version = getattr(
        bilitool, "__version__", importlib.metadata.version("bilitool")
    )
    assert version
    assert LoginController
    assert UploadController
    assert FeedController


def test_controllers_instantiable():
    """LoginController / UploadController / FeedController 可正常实例化。"""
    from bilitool import LoginController, UploadController, FeedController

    login_controller = LoginController()
    upload_controller = UploadController()
    feed_controller = FeedController()
    assert login_controller is not None
    assert upload_controller is not None
    assert feed_controller is not None


def test_env_credentials_present():
    """.env.example 中包含 BILIBILI_USERNAME 与 BILIBILI_PASSWORD。"""
    username, password = load_env_example()
    assert username, "BILIBILI_USERNAME 为空"
    assert password, "BILIBILI_PASSWORD 为空"


def test_login_status_checked():
    """当前未登录，登录检查接口可调用。"""
    from bilitool import LoginController

    controller = LoginController()
    is_login = controller.check_bilibili_login()
    assert is_login is False, "预期当前未登录"


def test_qrcode_endpoint_reachable():
    """B站二维码登录接口可达。"""
    from bilitool import LoginController

    controller = LoginController()
    url, auth_code = controller.login_bili.get_tv_qrcode_url_and_auth_code()
    assert url.startswith("https://passport.bilibili.com")
    assert auth_code


def test_upload_entry_rejected_without_login():
    """
    在未登录状态下，upload_video_entry 接口可调用，但会在 preupload 阶段被拒绝。
    使用空临时文件触发上传流程，避免上传真实视频。
    """
    from bilitool import UploadController

    upload_controller = UploadController()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        upload_controller.upload_video_entry(
            video_path=tmp_path,
            yaml="",
            copyright=1,
            tid=21,
            title="测试视频-请勿审核",
            desc="测试接口可调用性",
            tag="测试,bilitool",
            source="",
            cover="",
            dynamic="",
            cdn="",
        )
        pytest.fail("未登录时应抛出异常")
    except Exception:
        # 预期因未登录导致 preupload 失败（返回非 JSON，解析失败）
        pass
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def print_summary():
    username, password = load_env_example()
    print("\n" + "=" * 60)
    print("B站视频上传功能可调用性测试结论")
    print("=" * 60)
    print(f"1. bilitool 依赖与 API 导入: OK")
    print(f"2. LoginController / UploadController / FeedController 实例化: OK")
    print(f"3. .env.example 凭据: USERNAME={username if username else '(empty)'}, PASSWORD={'*' * len(password) if password else '(empty)'}")
    print(f"4. 当前登录状态: 未登录")
    print(f"5. B站二维码登录接口: 可达")
    print(f"6. upload_video_entry 接口: 可调用，但在未登录时会被拒绝")
    print("\n重要提示:")
    print("- bilitool 0.1.3 仅支持二维码或 cookie.json 文件登录，不支持账号密码自动登录。")
    print("- 因此 .env.example 中的 BILIBILI_USERNAME / BILIBILI_PASSWORD 无法被当前版本直接用于自动登录并调用上传。")
    print("- 要实现自动上传，需要先人工扫码生成 cookie.json，再通过 login_bilibili_with_cookie_file 加载。")


if __name__ == "__main__":
    test_bilitool_imported()
    test_controllers_instantiable()
    test_env_credentials_present()
    test_login_status_checked()
    test_qrcode_endpoint_reachable()
    test_upload_entry_rejected_without_login()
    print_summary()
    print("\n所有测试通过。")
