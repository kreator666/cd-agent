"""测试智能分块策略。"""

from pathlib import Path

import pytest
from langchain_core.documents import Document

from comedy_agent.rag.chunker import DocumentChunker, _merge_small_chunks, _split_oversized


class TestUtilityFunctions:
    """工具函数测试。"""

    def test_merge_small_chunks(self):
        docs = [
            Document(page_content="a" * 50, metadata={}),
            Document(page_content="b" * 50, metadata={}),
            Document(page_content="c" * 500, metadata={}),
        ]
        merged = _merge_small_chunks(docs, min_size=100, max_size=1000)
        assert len(merged) == 2
        assert "a" * 50 in merged[0].page_content
        assert "b" * 50 in merged[0].page_content
        assert merged[1].page_content == "c" * 500

    def test_split_oversized(self):
        doc = Document(page_content="x" * 2000, metadata={"src": "test"})
        chunks = _split_oversized(doc, max_size=500, overlap=50)
        assert len(chunks) > 1
        assert all(len(c.page_content) <= 500 for c in chunks)
        assert chunks[0].metadata["src"] == "test"
        assert chunks[0].metadata["split"] is True


class TestFixedStrategy:
    """固定大小分块测试。"""

    def test_short_text_unchanged(self):
        docs = [Document(page_content="short text", metadata={"id": 1})]
        result = DocumentChunker.split_fixed(docs, chunk_size=1000, overlap=100)
        assert len(result) == 1
        assert result[0].page_content == "short text"
        assert result[0].metadata["strategy"] == "fixed"

    def test_long_text_split(self):
        text = "word " * 500  # ~2500 chars
        docs = [Document(page_content=text, metadata={})]
        result = DocumentChunker.split_fixed(docs, chunk_size=1000, overlap=100)
        assert len(result) >= 2
        assert all(r.metadata["strategy"] == "fixed" for r in result)

    def test_overlap(self):
        text = "abc " * 300
        docs = [Document(page_content=text, metadata={})]
        result = DocumentChunker.split_fixed(docs, chunk_size=500, overlap=50)
        # 相邻块应有重叠内容
        if len(result) >= 2:
            assert result[0].page_content[-30:] in result[1].page_content


class TestParagraphStrategy:
    """段落分块测试。"""

    def test_basic_paragraphs(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        docs = [Document(page_content=text, metadata={})]
        result = DocumentChunker.split_by_paragraph(
            docs, max_chunk_size=500, min_chunk_size=5
        )
        assert len(result) == 3
        assert result[0].page_content == "Paragraph one."
        assert result[1].page_content == "Paragraph two."

    def test_merge_small_paragraphs(self):
        text = "A.\n\nB.\n\n" + "C" * 1000
        docs = [Document(page_content=text, metadata={})]
        result = DocumentChunker.split_by_paragraph(docs, max_chunk_size=1500, min_chunk_size=50)
        # A 和 B 很小，应该被合并
        contents = [r.page_content for r in result]
        assert any("A." in c and "B." in c for c in contents)


class TestSceneStrategy:
    """场景分块测试。"""

    def test_split_by_scene_markers(self):
        text = """第一场 客厅
角色A：你好。
角色B：你好。

第二场 餐厅
角色A：吃饭了吗？
"""
        docs = [Document(page_content=text, metadata={"source": "script"})]
        result = DocumentChunker.split_by_scene(docs)
        assert len(result) >= 1
        # 至少有一个块包含客厅或餐厅
        assert any("客厅" in r.page_content or "餐厅" in r.page_content for r in result)

    def test_fallback_when_no_scene(self):
        text = "No scene markers here. Just plain text.\n\nAnother paragraph."
        docs = [Document(page_content=text, metadata={})]
        result = DocumentChunker.split_by_scene(docs)
        # 应降级为 paragraph 策略
        assert len(result) >= 1
        assert any(r.metadata.get("strategy") == "paragraph" for r in result)


class TestDialogueStrategy:
    """角色对话分块测试。"""

    def test_split_by_role(self):
        text = """郭德纲：大家好。
于谦：好。
郭德纲：今天来说段相声。
于谦：请吧。

【旁白】这是舞台说明。
"""
        docs = [Document(page_content=text, metadata={})]
        result = DocumentChunker.split_by_dialogue(docs)
        roles = {r.metadata.get("role", "") for r in result}
        assert "郭德纲" in roles
        assert "于谦" in roles
        assert "narration" in roles

    def test_merge_small_dialogue(self):
        text = "郭德纲：短。\n于谦：嗯。\n郭德纲：又一句。"
        docs = [Document(page_content=text, metadata={})]
        result = DocumentChunker.split_by_dialogue(docs, min_chunk_size=10, max_chunk_size=500)
        # 交错对话不会跨角色合并，但同角色连续台词会合并
        guo_chunks = [r for r in result if r.metadata.get("role") == "郭德纲"]
        # 由于于谦在中间打断，郭德纲的台词分成两块
        assert len(guo_chunks) == 2
        assert any("短" in r.page_content for r in guo_chunks)
        assert any("又一句" in r.page_content for r in guo_chunks)
        # 于谦的块独立存在（不跨角色合并）
        yu_chunks = [r for r in result if r.metadata.get("role") == "于谦"]
        assert len(yu_chunks) == 1


class TestSubtitleStrategy:
    """字幕分块测试。"""

    def test_subtitle_window(self):
        docs = [
            Document(
                page_content="Hello",
                metadata={
                    "category": "subtitle",
                    "start_time": "00:00:01.000",
                    "end_time": "00:00:04.000",
                },
            )
        ]
        result = DocumentChunker.split_subtitles(docs, window_seconds=30.0)
        assert len(result) == 1
        assert result[0].metadata["strategy"] == "subtitle_window"
        assert result[0].metadata["window_start"] == 1.0
        assert result[0].metadata["window_end"] == 4.0

    def test_non_subtitle_pass_through(self):
        docs = [Document(page_content="normal text", metadata={"category": "text"})]
        result = DocumentChunker.split_subtitles(docs)
        assert len(result) == 1
        assert result[0].page_content == "normal text"


class TestAutoSplit:
    """自动策略分发测试。"""

    def test_auto_fixed(self):
        docs = [Document(page_content="x" * 2000, metadata={})]
        result = DocumentChunker.auto_split(docs, strategy="fixed", chunk_size=500)
        assert len(result) > 1
        assert all(r.metadata["strategy"] == "fixed" for r in result)

    def test_auto_paragraph(self):
        text = "A.\n\nB."
        docs = [Document(page_content=text, metadata={})]
        result = DocumentChunker.auto_split(
            docs, strategy="paragraph", min_chunk_size=1
        )
        assert len(result) == 2

    def test_auto_unknown_strategy(self):
        with pytest.raises(ValueError, match="未知分块策略"):
            DocumentChunker.auto_split([], strategy="unknown")
