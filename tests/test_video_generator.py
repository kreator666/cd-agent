"""脱口秀视频生成服务单元测试。

所有测试均使用 mock 替代 302.AI 与 edge-tts，避免调用真实 API 和
消耗 Token。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from comedy_agent.services.video_generator import VideoConfig, VideoGenerator


@pytest.fixture
def dummy_ai302(monkeypatch):
    """将 AI302Client 替换为返回本地占位图的 mock。"""

    class DummyClient:
        def generate_image(self, prompt, **kwargs):
            save_dir = kwargs.get("save_dir")
            if save_dir is None:
                save_dir = Path(__file__).parent / "tmp_video_assets"
            save_dir = Path(save_dir)
            save_dir.mkdir(parents=True, exist_ok=True)
            img_path = save_dir / "000.png"
            Image.new("RGB", (1024, 1024), (255, 200, 180)).save(img_path)
            return [str(img_path)]

    monkeypatch.setattr(
        "comedy_agent.services.video_generator.AI302Client", DummyClient
    )
    yield


def test_video_generator_run_no_tts(dummy_ai302, tmp_path):
    """关闭 TTS 时，完整流水线应能生成有效 MP4。"""
    config = VideoConfig(style="minimal", tts_enabled=False, max_scenes=3)
    generator = VideoGenerator(
        job_id="testjob01",
        result_id="result01",
        user_id="admin",
        script_text="今天天气真好。我去公园散步。看到一只可爱的小狗。",
        config=config,
        output_dir=tmp_path,
    )
    final_path = generator.run()

    assert Path(final_path).exists()
    assert Path(final_path).stat().st_size > 0


def _make_generator(style: str) -> VideoGenerator:
    return VideoGenerator(
        job_id="testjob02",
        result_id="result02",
        user_id="admin",
        script_text="测试文本",
        config=VideoConfig(style=style),
        output_dir=Path("."),
    )


def test_comic_strip_prompt_multi_panel_lineart():
    """爆笑漫画风：多格黑白线稿 + 夸张搞笑 + 无文字气泡。"""
    prompt = _make_generator("comic_strip")._build_image_prompt(
        "老板晚上十点在群里发消息，配图是空无一人的办公室"
    )
    assert "黑白线稿" in prompt
    assert "2到4格" in prompt
    assert "夸张搞笑" in prompt
    assert "不要上色" in prompt
    assert "无对话气泡" in prompt
    assert "画面内容" in prompt


def test_legacy_style_prompt_unchanged():
    """旧风格提示词保持原样（无对话气泡等仅属漫画风）。"""
    prompt = _make_generator("illustration")._build_image_prompt("今天天气真好")
    assert "治愈系插画风格" in prompt
    assert "无文字，无字幕" in prompt
    assert "无对话气泡" not in prompt


def test_unknown_style_falls_back_to_default():
    prompt = _make_generator("nonexistent")._build_image_prompt("abc")
    assert "治愈系插画风格" in prompt
