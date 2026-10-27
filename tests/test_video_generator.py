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
