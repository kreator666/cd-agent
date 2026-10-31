"""视频任务响应模型测试：silent_url 与 video_url 的推导。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from comedy_agent.api.routers.video import _job_to_response


def _make_job(tmp_path: Path, monkeypatch, *, with_silent: bool, with_final: bool):
    """构造一个最小可用的 VideoJob 替身。"""
    output_dir = tmp_path / "video"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "comedy_agent.api.routers.video.settings.video_output_dir", str(output_dir)
    )

    silent_path = output_dir / "job1" / "silent.mp4"
    final_path = output_dir / "job1" / "final.mp4"
    silent_path.parent.mkdir(parents=True, exist_ok=True)
    if with_silent:
        silent_path.write_bytes(b"silent")
    if with_final:
        final_path.write_bytes(b"final")

    return SimpleNamespace(
        job_id="job1",
        result_id="r1",
        status="running",
        stage="video",
        stages=[{"name": "script", "label": "剧本分镜", "status": "done", "message": ""}],
        storyboard_json=None,
        final_video_path=str(final_path) if with_final else None,
        video_path=str(silent_path) if with_silent else None,
        result=None,
        error=None,
        created_at=datetime(2026, 10, 30),
        updated_at=datetime(2026, 10, 30),
    )


def test_video_stage_has_silent_url_without_final(tmp_path, monkeypatch):
    """视频合成阶段：只有无声视频时，silent_url 可用、video_url 为空。"""
    job = _make_job(tmp_path, monkeypatch, with_silent=True, with_final=False)
    resp = _job_to_response(job)
    assert resp.silent_url == "/static/video/job1/silent.mp4"
    assert resp.video_url is None


def test_post_stage_has_both_urls(tmp_path, monkeypatch):
    """后期配音完成后：silent_url 与 video_url（成片）都有。"""
    job = _make_job(tmp_path, monkeypatch, with_silent=True, with_final=True)
    resp = _job_to_response(job)
    assert resp.silent_url == "/static/video/job1/silent.mp4"
    assert resp.video_url == "/static/video/job1/final.mp4"


def test_no_videos_no_urls(tmp_path, monkeypatch):
    job = _make_job(tmp_path, monkeypatch, with_silent=False, with_final=False)
    resp = _job_to_response(job)
    assert resp.silent_url is None
    assert resp.video_url is None
