"""Pytest 全局配置与共享 fixtures。"""

from __future__ import annotations

from unittest.mock import MagicMock

from pydantic import BaseModel


def pytest_addoption(parser):
    """添加自定义命令行选项。"""
    parser.addoption(
        "--full-lifespan",
        action="store_true",
        default=False,
        help="在 test_api_server.py 中执行完整的 lifespan（包括 VectorStore 模型加载），默认会 mock 跳过以加速测试",
    )


def make_structured_mock_llm(
    responses: dict[type[BaseModel], BaseModel | list[BaseModel]] | None = None,
    plain_content: str = "mocked plain response",
) -> MagicMock:
    """构造一个同时支持普通 invoke 和结构化输出的 mock LLM。

    Args:
        responses: 按 Schema 类映射的固定返回值；值为列表时按调用次数返回。
        plain_content: 普通 ``llm.invoke`` 返回的 content。

    Returns:
        配置好的 MagicMock LLM。
    """
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=plain_content)

    mapping = responses or {}

    def _with_structured_output(schema):
        structured = MagicMock()
        resp = mapping.get(schema)
        if isinstance(resp, list):
            iterator = iter(resp)
            structured.invoke.side_effect = lambda *args, **kwargs: next(iterator)
        elif resp is not None:
            structured.invoke.return_value = resp
        else:
            structured.invoke.return_value = MagicMock()
        return structured

    llm.with_structured_output.side_effect = _with_structured_output
    return llm
