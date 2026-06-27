"""验证理论知识语料库与清单文件的结构正确性。"""

import json
from pathlib import Path

import pytest

from comedy_agent.rag.chunker import DocumentChunker
from comedy_agent.rag.document_loader import DocumentLoader


KNOWLEDGE_DIR = Path(__file__).parent.parent / "data" / "knowledge"
CORPUS_PATH = KNOWLEDGE_DIR / "theory_corpus.md"
MANIFEST_PATH = KNOWLEDGE_DIR / "theory_manifest.json"


class TestTheoryCorpus:
    """理论语料库基础校验。"""

    def test_corpus_file_exists(self):
        assert CORPUS_PATH.exists(), "theory_corpus.md 必须存在"

    def test_manifest_file_exists_and_valid_json(self):
        assert MANIFEST_PATH.exists(), "theory_manifest.json 必须存在"
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        assert "items" in data
        assert len(data["items"]) >= 10, "核心理论条目应不少于 10 条"

    def test_manifest_items_have_required_fields(self):
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        valid_categories = {"concept", "technique", "pattern", "rule"}
        for item in data["items"]:
            assert "id" in item
            assert "title" in item
            assert "category" in item
            assert item["category"] in valid_categories
            assert "source" in item

    def test_corpus_loadable_by_document_loader(self):
        docs = DocumentLoader.load(CORPUS_PATH)
        assert len(docs) == 1, "Markdown 应被加载为单个 Document"
        assert len(docs[0].page_content) > 1000, "语料内容不应过短"

    def test_corpus_chunkable_by_paragraph_strategy(self):
        docs = DocumentLoader.load(CORPUS_PATH)
        chunks = DocumentChunker.split_by_paragraph(docs)
        item_count = len(json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["items"])
        # 段落分块会合并极小段落，因此 chunk 数在条目数的 70% 以上即可接受
        assert len(chunks) >= int(item_count * 0.7), f"按段落分块后得到 {len(chunks)} 个 chunk，过少"

    def test_corpus_chunks_contain_metadata_markers(self):
        docs = DocumentLoader.load(CORPUS_PATH)
        chunks = DocumentChunker.split_by_paragraph(docs)
        category_markers = ["类别:", "来源:"]
        matched = 0
        for chunk in chunks:
            if all(marker in chunk.page_content for marker in category_markers):
                matched += 1
        # 至少 80% 的 chunk 应包含类别/来源标记
        assert matched / len(chunks) >= 0.8, f"只有 {matched}/{len(chunks)} chunk 包含元数据标记"

    def test_manifest_titles_appear_in_corpus(self):
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        corpus_text = CORPUS_PATH.read_text(encoding="utf-8")
        missing = []
        for item in data["items"]:
            title = item["title"]
            if title not in corpus_text:
                missing.append(title)
        assert not missing, f"以下清单标题未在语料中出现: {missing}"
