"""302.AI 统一 API 客户端。

当前封装：
- 文生图：POST /v1/images/generations
- 文字转语音：POST /v1/audio/speech

均为 OpenAI 兼容接口，BASE_URL 使用 https://api.302.ai。
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.302.ai"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_TTS_MODEL = "tts-1"
DEFAULT_TTS_VOICE = "alloy"


class AI302Client:
    """轻量级 302.AI HTTP 客户端。"""

    def __init__(self, api_key: str | None = None, base_url: str = BASE_URL) -> None:
        self.api_key = api_key or settings.ai302_api_key
        self.base_url = base_url.rstrip("/")
        if not self.api_key:
            raise RuntimeError("AI302_API_KEY 未配置")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate_image(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_IMAGE_MODEL,
        size: str = "1024x1024",
        output_format: str = "png",
        quality: str = "medium",
        n: int = 1,
        save_dir: str | Path | None = None,
    ) -> list[str]:
        """调用 302.AI 文生图接口，返回图片本地路径或 URL 列表。

        Args:
            prompt: 图片描述（中文即可）。
            model: 模型名称，默认 gpt-image-2。
            size: 图片尺寸。
            output_format: 输出格式。
            quality: 质量。
            n: 生成数量。
            save_dir: 若提供，则将 base64 图片保存到该目录并返回本地路径。

        Returns:
            图片本地路径或 URL 列表。
        """
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size,
            "quality": quality,
            "output_format": output_format,
        }
        url = f"{self.base_url}/v1/images/generations"
        logger.info("[302.AI] 生成图片: model=%s prompt=%s...", model, prompt[:40])
        try:
            response = httpx.post(url, headers=self._headers(), json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            results: list[str] = []
            for idx, item in enumerate(data.get("data", [])):
                if item.get("url"):
                    results.append(item["url"])
                elif item.get("b64_json") and save_dir:
                    save_dir = Path(save_dir)
                    save_dir.mkdir(parents=True, exist_ok=True)
                    img_path = save_dir / f"{idx:03d}.{output_format}"
                    img_path.write_bytes(base64.b64decode(item["b64_json"]))
                    results.append(str(img_path))
            if not results:
                raise RuntimeError(f"图片生成未返回可用数据: {data}")
            return results
        except httpx.HTTPStatusError as exc:
            logger.error("[302.AI] 文生图失败: %s %s", exc.response.status_code, exc.response.text)
            raise
        except Exception:
            logger.exception("[302.AI] 文生图异常")
            raise

    def text_to_speech(
        self,
        text: str,
        *,
        model: str = DEFAULT_TTS_MODEL,
        voice: str = DEFAULT_TTS_VOICE,
        response_format: str = "mp3",
        speed: float = 1.0,
    ) -> bytes:
        """调用 302.AI TTS 接口，返回音频二进制数据。

        Args:
            text: 要朗读的文本，最长 4096 字符。
            model: TTS 模型，默认 tts-1。
            voice: 音色。
            response_format: 音频格式。
            speed: 语速。

        Returns:
            音频文件二进制内容。
        """
        if len(text) > 4096:
            text = text[:4096]
        payload: dict[str, Any] = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": response_format,
            "speed": speed,
        }
        url = f"{self.base_url}/v1/audio/speech"
        logger.info("[302.AI] TTS: voice=%s text=%s...", voice, text[:40])
        try:
            response = httpx.post(url, headers=self._headers(), json=payload, timeout=120)
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as exc:
            logger.error("[302.AI] TTS 失败: %s %s", exc.response.status_code, exc.response.text)
            raise
        except Exception:
            logger.exception("[302.AI] TTS 异常")
            raise

    @staticmethod
    def save_audio(audio_bytes: bytes, path: str | Path) -> Path:
        """保存音频到本地文件。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio_bytes)
        return path


def _b64_to_data_url(b64_string: str, mime_type: str = "image/png") -> str:
    """将 base64 字符串转为 data URL（备用）。"""
    return f"data:{mime_type};base64,{b64_string}"
