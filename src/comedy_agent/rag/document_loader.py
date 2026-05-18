"""文档加载流水线 —— 支持 PDF / Word / 网页 / 文本 / 字幕的解析入库。

基于 unstructured 实现多格式解析，失败时自动降级到纯 Python 方案。
为避免 Windows 上 heavy NLP 依赖导致的导入问题，unstructured 采用完全延迟导入策略。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# 可选依赖检测（仅做标记，不实际导入 heavy 模块）
# ------------------------------------------------------------------ #
try:
    import httpx

    _HAS_HTTPX = True
except ImportError:  # pragma: no cover
    _HAS_HTTPX = False

# ------------------------------------------------------------------ #
# 文件类型映射
# ------------------------------------------------------------------ #

# 纯文本类扩展名（不走 unstructured，直接读取）
_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".json", ".csv"}

# 字幕扩展名
_SUBTITLE_EXTENSIONS = {".srt", ".ass", ".vtt", ".ssa"}

# 需要 unstructured 解析的扩展名
_UNSTRUCTURED_EXTENSIONS = {".pdf", ".docx", ".doc", ".html", ".htm"}

_ALL_SUPPORTED = _TEXT_EXTENSIONS | _SUBTITLE_EXTENSIONS | _UNSTRUCTURED_EXTENSIONS


# ------------------------------------------------------------------ #
# 字幕解析器
# ------------------------------------------------------------------ #

_SRT_BLOCK_RE = re.compile(
    r"(\d+)\s*\n"
    r"(\d{1,2}:\d{2}:\d{2}[,.]\d{2,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{2,3})\s*\n"
    r"(.+?)(?=\n\n|\n\d+\s*\n|\Z)",
    re.DOTALL,
)

_VTT_BLOCK_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[,.]\d{2,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{2,3})\s*\n"
    r"(.+?)(?=\n\n|\Z)",
    re.DOTALL,
)

_ASS_DIALOGUE_RE = re.compile(
    r"Dialogue:\s*[^,]*,\s*([^,]*),\s*([^,]*),\s*[^,]*,\s*[^,]*,\s*[^,]*,\s*[^,]*,\s*[^,]*,\s*(.*)",
)


def _parse_srt(text: str) -> list[dict[str, Any]]:
    """解析 SRT 字幕格式。"""
    results: list[dict[str, Any]] = []
    for m in _SRT_BLOCK_RE.finditer(text):
        idx, start, end, content = m.groups()
        results.append(
            {
                "index": int(idx),
                "start": start.replace(",", "."),
                "end": end.replace(",", "."),
                "text": content.replace("\n", " ").strip(),
            }
        )
    return results


def _parse_vtt(text: str) -> list[dict[str, Any]]:
    """解析 WebVTT 字幕格式。"""
    lines = text.splitlines()
    while lines and not _VTT_BLOCK_RE.search(lines[0] if lines else ""):
        if lines[0].strip().startswith("WEBVTT") or lines[0].strip() == "":
            lines.pop(0)
        else:
            break
    body = "\n".join(lines)
    results: list[dict[str, Any]] = []
    for m in _VTT_BLOCK_RE.finditer(body):
        start, end, content = m.groups()
        results.append(
            {
                "start": start.replace(",", "."),
                "end": end.replace(",", "."),
                "text": content.replace("\n", " ").strip(),
            }
        )
    return results


def _parse_ass(text: str) -> list[dict[str, Any]]:
    """解析 ASS/SSA 字幕格式。"""
    results: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("Dialogue:"):
            continue
        body = line[len("Dialogue:") :]
        parts = body.split(",", 9)
        if len(parts) < 10:
            continue
        start, end, content = parts[1].strip(), parts[2].strip(), parts[9].strip()
        results.append(
            {
                "start": start,
                "end": end,
                "text": content.replace("\\N", " ").replace("\\n", " "),
            }
        )
    return results


def _load_subtitle(file_path: Path) -> list[Document]:
    """加载字幕文件为 Document 列表。"""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    suffix = file_path.suffix.lower()

    if suffix == ".srt":
        blocks = _parse_srt(text)
    elif suffix == ".vtt":
        blocks = _parse_vtt(text)
    elif suffix in (".ass", ".ssa"):
        blocks = _parse_ass(text)
    else:
        blocks = []

    docs: list[Document] = []
    for blk in blocks:
        docs.append(
            Document(
                page_content=blk["text"],
                metadata={
                    "source": str(file_path),
                    "file_type": suffix.lstrip("."),
                    "start_time": blk.get("start", ""),
                    "end_time": blk.get("end", ""),
                    "index": blk.get("index", 0),
                    "category": "subtitle",
                },
            )
        )
    return docs


# ------------------------------------------------------------------ #
# 主加载器
# ------------------------------------------------------------------ #


class DocumentLoader:
    """喜剧知识库文档加载器。

    支持格式：PDF、Word(docx)、HTML/网页、纯文本(txt/md)、字幕(SRT/ASS/VTT)。
    纯文本与字幕不走 unstructured，避免 heavy NLP 依赖导致的兼容性问题。
    """

    @classmethod
    def load(cls, file_path: str | Path) -> list[Document]:
        """加载单个文件，返回 Document 列表。

        Args:
            file_path: 文件路径。

        Returns:
            list[Document]: 解析后的文档列表。
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        suffix = path.suffix.lower()
        if suffix in _SUBTITLE_EXTENSIONS:
            return _load_subtitle(path)
        if suffix in _TEXT_EXTENSIONS:
            return cls._load_text(path)
        if suffix in _UNSTRUCTURED_EXTENSIONS:
            return cls._load_with_unstructured(path)

        # 未知扩展名：尝试纯文本读取作为兜底
        logger.warning("未知文件类型 %s，尝试纯文本读取", suffix)
        return cls._load_text(path)

    @classmethod
    def load_directory(
        cls,
        dir_path: str | Path,
        pattern: str = "*",
        recursive: bool = True,
    ) -> list[Document]:
        """批量加载目录下所有支持的文件。

        Args:
            dir_path: 目录路径。
            pattern: glob 匹配模式，如 ``*.pdf``。
            recursive: 是否递归子目录。

        Returns:
            list[Document]: 合并后的文档列表。
        """
        path = Path(dir_path)
        if not path.is_dir():
            raise NotADirectoryError(f"不是目录: {path}")

        docs: list[Document] = []
        iterator = path.rglob(pattern) if recursive else path.glob(pattern)
        for fp in iterator:
            if fp.is_file() and fp.suffix.lower() in _ALL_SUPPORTED:
                try:
                    docs.extend(cls.load(fp))
                except Exception as e:
                    logger.warning("加载 %s 失败: %s", fp, e)
        return docs

    @classmethod
    def load_url(cls, url: str, timeout: float = 30.0) -> list[Document]:
        """加载网页内容。

        Args:
            url: 网页 URL。
            timeout: 请求超时秒数。

        Returns:
            list[Document]: 解析后的文档列表。
        """
        if not _HAS_HTTPX:
            raise ImportError("加载网页需要 httpx，请运行: pip install httpx")

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"非法 URL: {url}")

        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type.lower():
            logger.warning("URL 返回非 HTML 内容: %s", content_type)

        # 尝试 unstructured 解析 HTML
        try:
            from unstructured.partition.html import partition_html

            elements = partition_html(text=resp.text)
            return cls._elements_to_docs(elements, source=url, file_type="html")
        except Exception as e:
            logger.warning("unstructured 解析网页失败，降级: %s", e)

        # 降级：简单文本提取
        return [
            Document(
                page_content=resp.text,
                metadata={"source": url, "file_type": "html", "category": "webpage"},
            )
        ]

    # ------------------------------------------------------------------ #
    # 纯文本加载（不依赖 unstructured）
    # ------------------------------------------------------------------ #
    @staticmethod
    def _load_text(path: Path) -> list[Document]:
        """直接读取纯文本文件。"""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            text = path.read_bytes().decode("utf-8", errors="replace")

        return [
            Document(
                page_content=text,
                metadata={
                    "source": str(path),
                    "file_type": path.suffix.lstrip(".").lower(),
                    "category": "text",
                },
            )
        ]

    # ------------------------------------------------------------------ #
    # unstructured 解析（延迟导入，仅复杂格式使用）
    # ------------------------------------------------------------------ #
    @classmethod
    def _load_with_unstructured(cls, path: Path) -> list[Document]:
        """使用 unstructured 解析文件。"""
        try:
            from unstructured.partition.auto import partition

            elements = partition(str(path))
            return cls._elements_to_docs(
                elements,
                source=str(path),
                file_type=path.suffix.lstrip(".").lower(),
            )
        except Exception as e:
            logger.warning("unstructured 解析 %s 失败，降级: %s", path, e)
            return cls._load_text(path)

    @staticmethod
    def _elements_to_docs(
        elements: list[Any],
        source: str,
        file_type: str,
    ) -> list[Document]:
        """将 unstructured Element 列表转为 Document 列表。"""
        docs: list[Document] = []
        for idx, el in enumerate(elements):
            text = str(el)
            if not text.strip():
                continue
            meta: dict[str, Any] = {
                "source": source,
                "file_type": file_type,
                "element_index": idx,
            }
            # 提取 unstructured 元数据
            if hasattr(el, "metadata"):
                el_meta = el.metadata
                if hasattr(el_meta, "page_number"):
                    meta["page_number"] = el_meta.page_number
                if hasattr(el_meta, "category"):
                    meta["category"] = el_meta.category
                elif hasattr(el, "category"):
                    meta["category"] = el.category
            docs.append(Document(page_content=text, metadata=meta))
        return docs
