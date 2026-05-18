"""测试文档加载流水线。"""

from pathlib import Path

import pytest
from langchain_core.documents import Document

from comedy_agent.rag.document_loader import (
    DocumentLoader,
    _parse_ass,
    _parse_srt,
    _parse_vtt,
)


class TestSubtitleParsers:
    """字幕解析器单元测试。"""

    def test_parse_srt_basic(self):
        text = """1
00:00:01,000 --> 00:00:04,000
First subtitle

2
00:00:05,000 --> 00:00:07,000
Second subtitle
with newline
"""
        blocks = _parse_srt(text)
        assert len(blocks) == 2
        assert blocks[0]["index"] == 1
        assert blocks[0]["start"] == "00:00:01.000"
        assert blocks[0]["text"] == "First subtitle"
        assert blocks[1]["text"] == "Second subtitle with newline"

    def test_parse_vtt_basic(self):
        text = """WEBVTT

00:00:01.000 --> 00:00:04.000
Hello world

00:00:05.000 --> 00:00:07.000
Second line
"""
        blocks = _parse_vtt(text)
        assert len(blocks) == 2
        assert blocks[0]["text"] == "Hello world"

    def test_parse_ass_basic(self):
        text = """[Script Info]
Title: Test

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default, Arial, 20, &H00FFFFFF, &H000000FF, &H00000000, &H00000000, 0, 0, 0, 0, 100, 100, 0, 0, 1, 2, 2, 2, 10, 10, 10, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,First line
Dialogue: 0,0:00:05.00,0:00:07.00,Default,,0,0,0,,Second line
"""
        blocks = _parse_ass(text)
        assert len(blocks) == 2
        assert blocks[0]["text"] == "First line"
        assert blocks[0]["start"] == "0:00:01.00"
        assert blocks[1]["text"] == "Second line"


class TestDocumentLoader:
    """DocumentLoader 集成测试。"""

    def test_load_txt(self, tmp_path: Path):
        fp = tmp_path / "test.txt"
        fp.write_text("This is test text.\nSecond line.", encoding="utf-8")
        docs = DocumentLoader.load(fp)
        assert len(docs) >= 1
        assert "test text" in docs[0].page_content
        assert docs[0].metadata["source"] == str(fp)
        assert docs[0].metadata["file_type"] == "txt"

    def test_load_md(self, tmp_path: Path):
        fp = tmp_path / "test.md"
        fp.write_text("# Title\n\nBody content.", encoding="utf-8")
        docs = DocumentLoader.load(fp)
        assert len(docs) >= 1
        assert "Body content" in docs[0].page_content or "Title" in docs[0].page_content

    def test_load_srt(self, tmp_path: Path):
        fp = tmp_path / "test.srt"
        fp.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\nSubtitle content\n\n",
            encoding="utf-8",
        )
        docs = DocumentLoader.load(fp)
        assert len(docs) == 1
        assert docs[0].page_content == "Subtitle content"
        assert docs[0].metadata["file_type"] == "srt"
        assert docs[0].metadata["start_time"] == "00:00:01.000"
        assert docs[0].metadata["end_time"] == "00:00:04.000"
        assert docs[0].metadata["category"] == "subtitle"

    def test_load_ass(self, tmp_path: Path):
        fp = tmp_path / "test.ass"
        fp.write_text(
            "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,ASS subtitle\n",
            encoding="utf-8",
        )
        docs = DocumentLoader.load(fp)
        assert len(docs) == 1
        assert docs[0].page_content == "ASS subtitle"
        assert docs[0].metadata["file_type"] == "ass"

    def test_load_directory(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("FileA", encoding="utf-8")
        (tmp_path / "b.txt").write_text("FileB", encoding="utf-8")
        docs = DocumentLoader.load_directory(tmp_path, pattern="*.txt")
        contents = {d.page_content for d in docs}
        assert "FileA" in contents
        assert "FileB" in contents

    def test_load_directory_recursive(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "root.txt").write_text("Root", encoding="utf-8")
        (sub / "deep.txt").write_text("Deep", encoding="utf-8")
        docs = DocumentLoader.load_directory(tmp_path, pattern="*.txt", recursive=True)
        contents = {d.page_content for d in docs}
        assert "Root" in contents
        assert "Deep" in contents

    def test_load_not_found(self):
        with pytest.raises(FileNotFoundError):
            DocumentLoader.load("/nonexistent/file.txt")

    def test_load_directory_not_a_dir(self, tmp_path: Path):
        fp = tmp_path / "not_dir.txt"
        fp.write_text("x")
        with pytest.raises(NotADirectoryError):
            DocumentLoader.load_directory(fp)

    def test_load_text_internal(self, tmp_path: Path):
        """直接测试纯文本读取方法。"""
        fp = tmp_path / "unknown.xyz"
        fp.write_text("fallback content")
        docs = DocumentLoader._load_text(fp)
        assert len(docs) == 1
        assert docs[0].page_content == "fallback content"
