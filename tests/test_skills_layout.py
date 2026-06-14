"""排版 Skill 测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.models.factory import ModelFactory
from comedy_agent.skills.layout import LayoutSkill


@pytest.fixture
def skill() -> LayoutSkill:
    return LayoutSkill()


def test_normalize_platform(skill: LayoutSkill) -> None:
    assert skill._normalize_platform("wechat") == "wechat"
    assert skill._normalize_platform("微信公众号") == "wechat"
    assert skill._normalize_platform("小红书") == "xiaohongshu"
    assert skill._normalize_platform("知乎") == "zhihu"
    assert skill._normalize_platform("b站") == "bilibili"
    assert skill._normalize_platform("unknown") == "wechat"


def test_run_empty_text(skill: LayoutSkill) -> None:
    assert skill._run(text="", platform="wechat") == "请输入需要排版的内容。"


def test_fallback_format_wechat(skill: LayoutSkill) -> None:
    text = "第一段\n\n第二段"
    result = skill._fallback_format(text, "wechat")
    assert "# 微信公众号排版" in result
    assert "第一段" in result
    assert "第二段" in result


def test_fallback_format_xiaohongshu(skill: LayoutSkill) -> None:
    text = "第一段\n\n第二段"
    result = skill._fallback_format(text, "xiaohongshu")
    assert "# 📝 小红书排版" in result
    assert "✨" in result


def test_run_fallback_on_llm_error(skill: LayoutSkill) -> None:
    with (
        patch.object(
            ModelFactory,
            "get_model_with_fallback",
            side_effect=RuntimeError("model error"),
        ),
        patch.object(skill, "_fallback_format", return_value="fallback result") as mock_fallback,
    ):
        result = skill._run(text="原文", platform="zhihu")
    assert result == "fallback result"
    mock_fallback.assert_called_once()


@pytest.mark.asyncio
async def test_arun_delegates_to_run(skill: LayoutSkill) -> None:
    with patch.object(skill, "_run", return_value="async layout") as mock_run:
        result = await skill._arun(text="原文", platform="wechat")
    assert result == "async layout"
    mock_run.assert_called_once()
