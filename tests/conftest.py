"""Pytest 全局配置与共享 fixtures。"""


def pytest_addoption(parser):
    """添加自定义命令行选项。"""
    parser.addoption(
        "--full-lifespan",
        action="store_true",
        default=False,
        help="在 test_api_server.py 中执行完整的 lifespan（包括 VectorStore 模型加载），默认会 mock 跳过以加速测试",
    )
