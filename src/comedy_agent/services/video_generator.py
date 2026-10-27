"""脱口秀视频生成服务。

基于 302.AI 文生图 + edge-tts + MoviePy 的轻量流水线：
剧本分镜 -> 生成插画 -> 生成配音 -> 合成视频 -> 输出成片。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
)
from PIL import Image

from comedy_agent.core.config import settings
from comedy_agent.services.ai302_client import AI302Client

logger = logging.getLogger(__name__)

# 竖屏 9:16，适合短视频平台
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 24

DEFAULT_STYLE = "illustration"
STYLE_PRESETS: dict[str, dict[str, str]] = {
    "illustration": {
        "image_prefix": "治愈系插画风格，柔和光线，简洁背景，",
        "bg_color": "#F7F5F0",
        "text_color": "#2C2C2C",
        "accent_color": "#FF764A",
    },
    "comic": {
        "image_prefix": "美式漫画风格，粗黑边线，夸张表情，高对比度，",
        "bg_color": "#1A1A1A",
        "text_color": "#FFFFFF",
        "accent_color": "#FFD93D",
    },
    "minimal": {
        "image_prefix": "极简平面设计，大面积留白，柔和渐变色，",
        "bg_color": "#FFFFFF",
        "text_color": "#333333",
        "accent_color": "#FF764A",
    },
}


def _find_chinese_font() -> str:
    """跨平台查找可用的中文字体。"""
    candidates: list[str] = []
    system = os.name
    if system == "nt":  # Windows
        candidates = [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\simsun.ttc",
            r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
        ]
    else:
        # Linux / macOS 常见中文字体
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
    for path in candidates:
        if Path(path).exists():
            return path
    # 兜底：让 MoviePy 使用默认字体（中文会显示为方框，但不会崩溃）
    return ""


@dataclass
class Scene:
    """一个视频镜头。"""

    text: str = ""
    image_prompt: str = ""
    image_path: str | None = None
    audio_path: str | None = None
    duration: float = 3.0
    order: int = 0


@dataclass
class VideoConfig:
    """视频生成配置。"""

    style: str = DEFAULT_STYLE
    tts_enabled: bool = True
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    bgm_enabled: bool = False
    bgm_path: str | None = None
    pace: str = "normal"  # slow / normal / fast
    max_scenes: int = 5


class VideoGenerator:
    """脱口秀视频生成器。"""

    def __init__(
        self,
        job_id: str,
        result_id: str,
        user_id: str,
        script_text: str,
        config: VideoConfig | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self.job_id = job_id
        self.result_id = result_id
        self.user_id = user_id
        self.script_text = script_text.strip()
        self.config = config or VideoConfig()
        self.output_dir = output_dir or (Path(settings.video_output_dir) / job_id)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ai302 = AI302Client()
        self.scenes: list[Scene] = []
        self.font_path = _find_chinese_font()
        self._stage_status: dict[str, dict[str, Any]] = {
            "script": {"status": "pending", "message": ""},
            "assets": {"status": "pending", "message": ""},
            "storyboard": {"status": "pending", "message": ""},
            "video": {"status": "pending", "message": ""},
            "post": {"status": "pending", "message": ""},
        }

    # ------------------------------------------------------------------ #
    # 状态更新辅助
    # ------------------------------------------------------------------ #

    def _set_stage(self, stage: str, status: str, message: str = "") -> None:
        self._stage_status[stage] = {"status": status, "message": message}
        logger.info("[video-%s] stage=%s status=%s %s", self.job_id, stage, status, message)

    def stage_summary(self) -> list[dict[str, Any]]:
        return [
            {"name": k, "label": self._stage_label(k), **v}
            for k, v in self._stage_status.items()
        ]

    @staticmethod
    def _stage_label(name: str) -> str:
        labels = {
            "script": "剧本分镜",
            "assets": "画面资产",
            "storyboard": "分镜预览",
            "video": "视频合成",
            "post": "后期配音",
        }
        return labels.get(name, name)

    # ------------------------------------------------------------------ #
    # Stage 1: 剧本分镜
    # ------------------------------------------------------------------ #

    def split_script(self) -> list[Scene]:
        """把段子文本切分为多个镜头。

        先按句子切分，再按 max_scenes 合并，保证每个镜头都有完整语义。
        """
        self._set_stage("script", "running", "正在拆分剧本")
        if not self.script_text:
            raise ValueError("段子内容为空")

        # 按中文标点切分句子
        sentences = re.split(r"(?<=[。！？\n])", self.script_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            sentences = [self.script_text]

        max_scenes = max(2, min(self.config.max_scenes, len(sentences)))
        # 尽量均匀合并
        chunks: list[list[str]] = [[] for _ in range(max_scenes)]
        for idx, sent in enumerate(sentences):
            chunks[idx % max_scenes].append(sent)

        scenes: list[Scene] = []
        for idx, chunk in enumerate(chunks):
            text = "".join(chunk)
            if not text:
                continue
            prompt = self._build_image_prompt(text)
            scenes.append(
                Scene(
                    text=text,
                    image_prompt=prompt,
                    order=idx,
                )
            )

        self.scenes = scenes
        self._set_stage("script", "done", f"拆分出 {len(scenes)} 个镜头")
        return scenes

    def _build_image_prompt(self, text: str) -> str:
        """根据镜头文本和风格构建文生图提示词。"""
        preset = STYLE_PRESETS.get(self.config.style, STYLE_PRESETS[DEFAULT_STYLE])
        prefix = preset["image_prefix"]
        # 提取关键词：去掉语气词，保留名词和动词
        keywords = re.sub(r"[，。！？、：；\"'""''（）()\[\]]", " ", text)
        keywords = re.sub(r"\s+", " ", keywords).strip()[:120]
        return f"{prefix}画面内容：{keywords}，无文字，无字幕，高画质"

    # ------------------------------------------------------------------ #
    # Stage 2: 画面资产
    # ------------------------------------------------------------------ #

    def generate_assets(self) -> list[str]:
        """为每个镜头生成插画。"""
        self._set_stage("assets", "running", "正在生成插画")
        if not self.scenes:
            self.split_script()

        image_dir = self.output_dir / "images"
        image_dir.mkdir(parents=True, exist_ok=True)

        paths: list[str] = []
        for scene in self.scenes:
            try:
                urls = self.ai302.generate_image(
                    scene.image_prompt,
                    model="gpt-image-2",
                    size="1024x1024",
                    save_dir=image_dir,
                )
                # 取第一个结果；如果是 URL 则下载到本地
                first = urls[0]
                local_path = self._ensure_local_image(first, image_dir, scene.order)
                scene.image_path = str(local_path)
                paths.append(scene.image_path)
            except Exception as exc:
                logger.exception("[video-%s] 镜头 %s 图片生成失败", self.job_id, scene.order)
                # 使用纯色占位图，避免整个任务失败
                placeholder = self._create_placeholder_image(image_dir, scene.order)
                scene.image_path = str(placeholder)
                paths.append(scene.image_path)

        self._set_stage("assets", "done", f"生成 {len(paths)} 张插画")
        return paths

    def _ensure_local_image(self, source: str, image_dir: Path, idx: int) -> Path:
        """将 URL 或 base64 图片保存为本地文件。"""
        target = image_dir / f"{idx:03d}.png"
        if source.startswith("http://") or source.startswith("https://"):
            response = httpx.get(source, timeout=60)
            response.raise_for_status()
            target.write_bytes(response.content)
        elif source.startswith("data:image"):
            # data URL
            b64 = source.split(",")[1]
            target.write_bytes(base64.b64decode(b64))  # type: ignore[arg-type]
        elif Path(source).exists():
            shutil.copy(source, target)
        else:
            raise ValueError(f"未知图片源: {source[:80]}")
        return target

    def _create_placeholder_image(self, image_dir: Path, idx: int) -> Path:
        """生成一张纯色占位图。"""
        target = image_dir / f"{idx:03d}.png"
        preset = STYLE_PRESETS.get(self.config.style, STYLE_PRESETS[DEFAULT_STYLE])
        bg_color = preset["bg_color"].lstrip("#")
        rgb = tuple(int(bg_color[i : i + 2], 16) for i in (0, 2, 4))
        img = Image.new("RGB", (1024, 1024), rgb)
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target)
        return target

    # ------------------------------------------------------------------ #
    # Stage 3: 分镜预览
    # ------------------------------------------------------------------ #

    def build_storyboard(self) -> dict[str, Any]:
        """构造分镜板数据。"""
        self._set_stage("storyboard", "running", "正在生成分镜")
        if not self.scenes or not self.scenes[0].image_path:
            self.generate_assets()

        storyboard = {
            "scenes": [
                {
                    "order": s.order,
                    "text": s.text,
                    "image_path": s.image_path,
                    "duration": s.duration,
                }
                for s in self.scenes
            ],
            "config": {
                "style": self.config.style,
                "tts_enabled": self.config.tts_enabled,
                "pace": self.config.pace,
            },
        }
        self._set_stage("storyboard", "done", "分镜生成完成")
        return storyboard

    # ------------------------------------------------------------------ #
    # Stage 4 & 5: 视频合成 + 后期配音
    # ------------------------------------------------------------------ #

    async def _generate_tts_for_scene(self, scene: Scene) -> None:
        """为单个镜头生成 edge-tts 音频。"""
        if not self.config.tts_enabled or not scene.text:
            return
        try:
            from edge_tts import Communicate

            audio_path = self.output_dir / "audio" / f"{scene.order:03d}.mp3"
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            communicate = Communicate(scene.text, voice=self.config.tts_voice)
            await communicate.save(str(audio_path))
            scene.audio_path = str(audio_path)
        except Exception:
            logger.exception("[video-%s] 镜头 %s TTS 失败", self.job_id, scene.order)

    async def generate_tts(self) -> None:
        """为所有镜头生成配音。"""
        if not self.config.tts_enabled:
            return
        self._set_stage("post", "running", "正在生成配音")
        await asyncio.gather(*[self._generate_tts_for_scene(s) for s in self.scenes])

    def _calculate_duration(self, scene: Scene) -> float:
        """计算镜头时长。"""
        if scene.audio_path and Path(scene.audio_path).exists():
            try:
                clip = AudioFileClip(scene.audio_path)
                duration = float(clip.duration)
                clip.close()
                return max(duration + 0.3, 1.5)
            except Exception:
                pass

        # 无配音时按字数估算
        chars = len(scene.text)
        pace_map = {"slow": 2.5, "normal": 3.5, "fast": 5.0}
        wps = pace_map.get(self.config.pace, 3.5)
        return max(chars / wps, 2.0)

    def compose_video(self) -> Path:
        """合成最终视频。"""
        self._set_stage("video", "running", "正在合成无声视频")
        if not self.scenes or not self.scenes[0].image_path:
            self.generate_assets()

        # 先生成配音并计算时长
        if self.config.tts_enabled:
            asyncio.run(self.generate_tts())

        for scene in self.scenes:
            scene.duration = self._calculate_duration(scene)

        clips: list[Any] = []
        for scene in self.scenes:
            clip = self._build_scene_clip(scene)
            clips.append(clip)

        video = concatenate_videoclips(clips, method="compose")

        # 添加 BGM（如有）
        if self.config.bgm_enabled and self.config.bgm_path and Path(self.config.bgm_path).exists():
            try:
                bgm = AudioFileClip(self.config.bgm_path).subclipped(0, video.duration)
                bgm = bgm.with_volume_scaled(0.15)
                if video.audio is not None:
                    video.audio = CompositeAudioClip([video.audio, bgm])
                else:
                    video.audio = bgm
            except Exception:
                logger.exception("[video-%s] BGM 合成失败", self.job_id)

        final_path = self.output_dir / "final.mp4"
        video.write_videofile(
            str(final_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            threads=2,
        )
        video.close()
        for clip in clips:
            clip.close()

        self._set_stage("video", "done", f"视频已保存: {final_path}")
        self._set_stage("post", "done", "后期配音完成")
        return final_path

    def _build_scene_clip(self, scene: Scene) -> CompositeVideoClip:
        """构建单个镜头的视频片段。"""
        preset = STYLE_PRESETS.get(self.config.style, STYLE_PRESETS[DEFAULT_STYLE])
        bg_color = preset["bg_color"]
        text_color = preset["text_color"]
        accent_color = preset["accent_color"]

        # 背景 + 图片
        if scene.image_path and Path(scene.image_path).exists():
            img_clip = ImageClip(scene.image_path).with_duration(scene.duration)
            # 按比例缩放填满宽度，居中裁剪高度
            img_w, img_h = img_clip.size
            scale = VIDEO_WIDTH / img_w
            new_h = int(img_h * scale)
            img_clip = img_clip.resized(scale)
            if new_h > VIDEO_HEIGHT:
                img_clip = img_clip.cropped(
                    x_center=VIDEO_WIDTH / 2,
                    y_center=new_h / 2,
                    width=VIDEO_WIDTH,
                    height=VIDEO_HEIGHT,
                )
            else:
                # 图片高度不足，居中放置，下方留字幕区
                img_clip = img_clip.with_position((0, (VIDEO_HEIGHT - new_h) * 0.25))
        else:
            img_clip = None

        # 底部字幕区背景
        subtitle_bg_height = 280
        subtitle_bg = (
            ImageClip(self._color_image(bg_color, VIDEO_WIDTH, subtitle_bg_height))
            .with_duration(scene.duration)
            .with_position((0, VIDEO_HEIGHT - subtitle_bg_height))
        )

        # 字幕文字
        subtitle_text = self._wrap_text(scene.text, max_chars=16)
        subtitle = (
            TextClip(
                text=subtitle_text,
                font=self.font_path or None,
                font_size=56,
                color=text_color,
                size=(VIDEO_WIDTH - 80, subtitle_bg_height - 60),
                method="caption",
                text_align="center",
                interline=-10,
            )
            .with_duration(scene.duration)
            .with_position((40, VIDEO_HEIGHT - subtitle_bg_height + 30))
        )

        # 装饰线
        accent_line = (
            ImageClip(self._color_image(accent_color, VIDEO_WIDTH, 6))
            .with_duration(scene.duration)
            .with_position((0, VIDEO_HEIGHT - subtitle_bg_height))
        )

        layers = [subtitle_bg, accent_line, subtitle]
        if img_clip is not None:
            layers.insert(0, img_clip)

        scene_clip = CompositeVideoClip(layers, size=(VIDEO_WIDTH, VIDEO_HEIGHT))
        scene_clip = scene_clip.with_duration(scene.duration)

        # 添加配音
        if scene.audio_path and Path(scene.audio_path).exists():
            try:
                audio = AudioFileClip(scene.audio_path)
                scene_clip = scene_clip.with_audio(audio)
            except Exception:
                logger.exception("[video-%s] 镜头 %s 音频加载失败", self.job_id, scene.order)

        return scene_clip

    @staticmethod
    def _wrap_text(text: str, max_chars: int = 16) -> str:
        """按 max_chars 自动换行（尽量在标点处换）。"""
        lines: list[str] = []
        current = ""
        for char in text:
            current += char
            if len(current) >= max_chars and char in "，。！？、；：":
                lines.append(current)
                current = ""
        if current:
            lines.append(current)
        return "\n".join(lines)

    @staticmethod
    def _color_image(hex_color: str, width: int, height: int) -> np.ndarray:
        """创建纯色图片数组。"""
        hex_color = hex_color.lstrip("#")
        rgb = [int(hex_color[i : i + 2], 16) for i in (0, 2, 4)]
        return np.full((height, width, 3), rgb, dtype=np.uint8)

    # ------------------------------------------------------------------ #
    # 完整流水线
    # ------------------------------------------------------------------ #

    def run(self) -> Path:
        """执行完整生成流程。"""
        self.split_script()
        self.generate_assets()
        self.build_storyboard()
        final_path = self.compose_video()
        return final_path


def config_from_dict(data: dict[str, Any]) -> VideoConfig:
    """从字典构造 VideoConfig。"""
    return VideoConfig(
        style=data.get("style", DEFAULT_STYLE),
        tts_enabled=data.get("tts_enabled", True),
        tts_voice=data.get("tts_voice", "zh-CN-XiaoxiaoNeural"),
        bgm_enabled=data.get("bgm_enabled", False),
        bgm_path=data.get("bgm_path"),
        pace=data.get("pace", "normal"),
        max_scenes=int(data.get("max_scenes", 5)),
    )
