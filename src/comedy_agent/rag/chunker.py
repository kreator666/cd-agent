"""智能分块策略 —— 按场景、笑点单元、角色对话分块，保留元数据。

提供多种分块策略，适配不同类型的喜剧文档：
- fixed: 通用固定大小分块
- paragraph: 按段落分块（适合理论书籍）
- scene: 按场景分块（适合剧本）
- dialogue: 按角色对话分块（适合相声/小品/情景喜剧）
- subtitle: 按时间窗口合并字幕（适合视频字幕）
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# 常量
# ------------------------------------------------------------------ #

# 场景分隔符正则：第X场、场景X、SCENE X、【场景】等
_SCENE_PATTERNS = [
    re.compile(r"^\s*(第[一二三四五六七八九十百零\d]+场|场景[：:]\s*.*)\s*$", re.MULTILINE),
    re.compile(r"^\s*【\s*场景.*?】\s*$", re.MULTILINE),
    re.compile(r"^\s*SCENE\s*\d*\s*[:：]?.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*={3,}\s*$", re.MULTILINE),  # === 分隔线
]

# 角色对话正则：角色名（中文1-8字）+ ：或 :
_DIALOGUE_PATTERN = re.compile(
    r"^\s*([\u4e00-\u9fa5]{1,8}[甲乙丙丁]?|[A-Za-z][A-Za-z\s]{0,15})[:：]\s*(.*)$",
    re.MULTILINE,
)

# 笑点/包袱标记
_PUNCHLINE_MARKERS = ["（笑）", "（掌声）", "（大笑）", "包袱", "笑点"]


# ------------------------------------------------------------------ #
# 工具函数
# ------------------------------------------------------------------ #


def _merge_small_chunks(
    chunks: list[Document],
    min_size: int = 200,
    max_size: int = 1500,
    respect_role: bool = False,
) -> list[Document]:
    """合并过小的相邻块，同时确保不超过最大大小。

    Args:
        chunks: 输入块列表。
        min_size: 合并前最小字符数。
        max_size: 合并后最大字符数。
        respect_role: 是否只在相同 role 之间合并（用于对话分块）。
    """
    if not chunks:
        return []

    merged: list[Document] = []
    current = chunks[0]

    for nxt in chunks[1:]:
        combined_len = len(current.page_content) + len(nxt.page_content) + 1
        can_merge = len(current.page_content) < min_size and combined_len <= max_size
        if respect_role:
            can_merge = can_merge and current.metadata.get("role") == nxt.metadata.get("role")
        if can_merge:
            current = Document(
                page_content=current.page_content + "\n" + nxt.page_content,
                metadata={**current.metadata, "merged": True},
            )
        else:
            merged.append(current)
            current = nxt
    merged.append(current)
    return merged


def _split_oversized(
    doc: Document,
    max_size: int = 1500,
    overlap: int = 100,
) -> list[Document]:
    """对超长文档按固定大小拆分，保留元数据。"""
    text = doc.page_content
    if len(text) <= max_size:
        return [doc]

    chunks: list[Document] = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + max_size
        # 尝试在句子边界切分
        if end < len(text):
            # 向前找最近的句号、问号、感叹号、换行
            for pos in range(end, start + max_size // 2, -1):
                if pos < len(text) and text[pos] in "。！？\n":
                    end = pos + 1
                    break
        chunk_text = text[start:end].strip()
        if chunk_text:
            meta = {**doc.metadata, "chunk_index": idx, "split": True}
            chunks.append(Document(page_content=chunk_text, metadata=meta))
            idx += 1
        start = end - overlap
    return chunks


# ------------------------------------------------------------------ #
# 分块策略
# ------------------------------------------------------------------ #


class DocumentChunker:
    """文档智能分块器。"""

    @staticmethod
    def split_fixed(
        documents: list[Document],
        chunk_size: int = 1000,
        overlap: int = 200,
    ) -> list[Document]:
        """固定大小分块（通用策略）。

        Args:
            documents: 输入文档列表。
            chunk_size: 每块最大字符数。
            overlap: 相邻块重叠字符数。

        Returns:
            list[Document]: 分块后的文档列表。
        """
        result: list[Document] = []
        for doc in documents:
            text = doc.page_content
            if len(text) <= chunk_size:
                result.append(
                    Document(
                        page_content=text,
                        metadata={**doc.metadata, "strategy": "fixed"},
                    )
                )
                continue

            start = 0
            idx = 0
            while start < len(text):
                end = start + chunk_size
                # 尽量在句子边界切分
                if end < len(text):
                    for pos in range(end, start + chunk_size // 2, -1):
                        if pos < len(text) and text[pos] in "。！？\n；":
                            end = pos + 1
                            break
                chunk_text = text[start:end].strip()
                if chunk_text:
                    meta = {
                        **doc.metadata,
                        "chunk_index": idx,
                        "strategy": "fixed",
                    }
                    result.append(Document(page_content=chunk_text, metadata=meta))
                    idx += 1
                start = max(start + 1, end - overlap)
        return result

    @staticmethod
    def split_by_paragraph(
        documents: list[Document],
        max_chunk_size: int = 1500,
        min_chunk_size: int = 200,
    ) -> list[Document]:
        """按段落分块（适合理论书籍、文章）。

        以空行或换行分隔段落，超长段落再拆，过小段落合并。

        Args:
            documents: 输入文档列表。
            max_chunk_size: 合并后最大字符数。
            min_chunk_size: 合并前最小字符数。

        Returns:
            list[Document]: 分块后的文档列表。
        """
        raw_chunks: list[Document] = []
        for doc in documents:
            paragraphs = re.split(r"\n\s*\n|\r\n\s*\r\n", doc.page_content)
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                if len(para) > max_chunk_size:
                    # 超长段落先拆
                    raw_chunks.extend(
                        _split_oversized(
                            Document(page_content=para, metadata=doc.metadata),
                            max_chunk_size,
                        )
                    )
                else:
                    raw_chunks.append(
                        Document(
                            page_content=para,
                            metadata={**doc.metadata, "strategy": "paragraph"},
                        )
                    )
        return _merge_small_chunks(raw_chunks, min_chunk_size, max_chunk_size, respect_role=True)

    @staticmethod
    def split_by_scene(
        documents: list[Document],
        max_chunk_size: int = 2000,
    ) -> list[Document]:
        """按场景分块（适合剧本类文档）。

        识别场景标题作为分隔符，将同一场景的内容聚合为一块。

        Args:
            documents: 输入文档列表。
            max_chunk_size: 单块最大字符数。

        Returns:
            list[Document]: 分块后的文档列表。
        """
        result: list[Document] = []
        for doc in documents:
            text = doc.page_content
            # 找到所有场景分隔位置
            split_positions: list[int] = [0]
            for pattern in _SCENE_PATTERNS:
                for m in pattern.finditer(text):
                    pos = m.start()
                    if pos not in split_positions:
                        split_positions.append(pos)
            split_positions.sort()
            split_positions.append(len(text))

            if len(split_positions) <= 2:
                # 未识别到场景，降级为段落分块
                result.extend(DocumentChunker.split_by_paragraph([doc], max_chunk_size))
                continue

            for i in range(len(split_positions) - 1):
                start, end = split_positions[i], split_positions[i + 1]
                chunk_text = text[start:end].strip()
                if not chunk_text:
                    continue
                meta = {
                    **doc.metadata,
                    "strategy": "scene",
                    "scene_index": i,
                }
                # 提取场景标题
                first_line = chunk_text.split("\n", 1)[0].strip()
                if first_line:
                    meta["scene_title"] = first_line[:100]

                if len(chunk_text) > max_chunk_size:
                    result.extend(
                        _split_oversized(
                            Document(page_content=chunk_text, metadata=meta),
                            max_chunk_size,
                        )
                    )
                else:
                    result.append(Document(page_content=chunk_text, metadata=meta))
        return result

    @staticmethod
    def split_by_dialogue(
        documents: list[Document],
        max_chunk_size: int = 1500,
        min_chunk_size: int = 100,
    ) -> list[Document]:
        """按角色对话分块（适合相声、小品、情景喜剧）。

        将同一角色的连续台词聚合，或按对话回合聚合。

        Args:
            documents: 输入文档列表。
            max_chunk_size: 合并后最大字符数。
            min_chunk_size: 合并前最小字符数。

        Returns:
            list[Document]: 分块后的文档列表。
        """
        raw_chunks: list[Document] = []
        for doc in documents:
            text = doc.page_content
            lines = text.splitlines()
            current_role: str | None = None
            current_lines: list[str] = []

            def _flush() -> None:
                if not current_lines:
                    return
                content = "\n".join(current_lines).strip()
                if content:
                    meta: dict[str, Any] = {
                        **doc.metadata,
                        "strategy": "dialogue",
                        "role": current_role or "unknown",
                    }
                    raw_chunks.append(Document(page_content=content, metadata=meta))
                current_lines.clear()

            for line in lines:
                m = _DIALOGUE_PATTERN.match(line)
                if m:
                    role, dialogue = m.groups()
                    if current_role is not None and role != current_role:
                        _flush()
                    current_role = role
                    current_lines.append(f"{role}：{dialogue}")
                else:
                    # 非对话行（舞台说明、场景描述等）
                    if current_lines:
                        _flush()
                        current_role = None
                    stripped = line.strip()
                    if stripped:
                        raw_chunks.append(
                            Document(
                                page_content=stripped,
                                metadata={
                                    **doc.metadata,
                                    "strategy": "dialogue",
                                    "role": "narration",
                                },
                            )
                        )
            _flush()

        return _merge_small_chunks(raw_chunks, min_chunk_size, max_chunk_size, respect_role=True)

    @staticmethod
    def split_subtitles(
        documents: list[Document],
        window_seconds: float = 30.0,
    ) -> list[Document]:
        """字幕按时间窗口合并分块。

        将一定时间范围内的字幕文本合并为一块，便于检索"某段时间讲了什么"。

        Args:
            documents: 输入文档列表（需包含 start_time / end_time 元数据）。
            window_seconds: 时间窗口秒数。

        Returns:
            list[Document]: 分块后的文档列表。
        """
        result: list[Document] = []
        for doc in documents:
            meta = doc.metadata
            if meta.get("category") != "subtitle":
                # 非字幕文档直接返回
                result.append(doc)
                continue

            start_str = str(meta.get("start_time", "0"))
            end_str = str(meta.get("end_time", "0"))

            def _to_seconds(t: str) -> float:
                """将时间字符串转为秒数。支持 00:00:00.000 / 0:00:00.00 等格式。"""
                t = t.strip().replace(",", ".")
                parts = t.split(":")
                try:
                    if len(parts) == 3:
                        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    if len(parts) == 2:
                        return float(parts[0]) * 60 + float(parts[1])
                    return float(parts[0])
                except (ValueError, IndexError):
                    return 0.0

            start_sec = _to_seconds(start_str)
            # 如果当前文档的时间窗口已经在 window_seconds 内，直接保留
            end_sec = _to_seconds(end_str)
            if end_sec - start_sec >= window_seconds:
                result.append(doc)
                continue

            meta_out = {
                **meta,
                "strategy": "subtitle_window",
                "window_start": start_sec,
                "window_end": end_sec,
            }
            result.append(Document(page_content=doc.page_content, metadata=meta_out))
        return result

    @classmethod
    def auto_split(
        cls,
        documents: list[Document],
        strategy: str = "paragraph",
        **kwargs: Any,
    ) -> list[Document]:
        """根据策略自动选择分块方式。

        Args:
            documents: 输入文档列表。
            strategy: 分块策略，可选 ``fixed`` / ``paragraph`` / ``scene`` / ``dialogue`` / ``subtitle``。
            **kwargs: 传递给具体策略的参数。

        Returns:
            list[Document]: 分块后的文档列表。
        """
        dispatch = {
            "fixed": cls.split_fixed,
            "paragraph": cls.split_by_paragraph,
            "scene": cls.split_by_scene,
            "dialogue": cls.split_by_dialogue,
            "subtitle": cls.split_subtitles,
        }
        fn = dispatch.get(strategy)
        if fn is None:
            raise ValueError(
                f"未知分块策略 '{strategy}'。可用策略: {list(dispatch.keys())}"
            )
        return fn(documents, **kwargs)
