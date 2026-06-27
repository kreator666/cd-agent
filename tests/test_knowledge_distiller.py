"""测试知识蒸馏器核心逻辑。"""

import json
from pathlib import Path

import pytest

from comedy_agent.core.knowledge_distiller import (
    DEFAULT_CORPUS_PATH,
    RawTheorySection,
    distill,
    parse_corpus,
    save_items,
)
from comedy_agent.core.knowledge_models import DistillationOutput, KnowledgeItem


class FakeStructuredLLM:
    """模拟支持结构化输出的 LLM。"""

    def __init__(self, items):
        self._items = items

    def invoke(self, messages):
        return DistillationOutput(items=self._items)


class FakeLLM:
    """模拟 LangChain ChatModel，仅实现 distill 所需接口。"""

    def __init__(self, items):
        self._items = items

    def with_structured_output(self, schema):
        return FakeStructuredLLM(self._items)


@pytest.fixture
def sample_sections():
    return [
        RawTheorySection(
            title="三番四抖",
            category="technique",
            source="comedy_theory.md",
            content="三番四抖是相声经典结构技巧...",
        ),
        RawTheorySection(
            title="不要解释笑点",
            category="rule",
            source="comedy_theory.md",
            content="笑点一旦被解释，笑果就会大打折扣...",
        ),
    ]


class TestParseCorpus:
    """解析理论语料测试。"""

    def test_parse_real_corpus(self):
        sections = parse_corpus(DEFAULT_CORPUS_PATH)
        assert len(sections) >= 10, f"期望至少 10 个段落，实际 {len(sections)}"

    def test_categories_are_valid(self):
        valid = {"concept", "technique", "pattern", "rule"}
        sections = parse_corpus(DEFAULT_CORPUS_PATH)
        for sec in sections:
            assert sec.category in valid, f"非法类别: {sec.category}"

    def test_titles_match_manifest(self):
        from comedy_agent.rag.document_loader import DocumentLoader

        manifest_path = DEFAULT_CORPUS_PATH.parent / "theory_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        titles = {item["title"] for item in manifest["items"]}
        sections = parse_corpus(DEFAULT_CORPUS_PATH)
        parsed_titles = {sec.title for sec in sections}
        assert titles.issubset(parsed_titles), f"缺失标题: {titles - parsed_titles}"


class TestDistill:
    """蒸馏逻辑测试。"""

    def test_distill_returns_knowledge_items(self, sample_sections):
        fake_items = [
            KnowledgeItem(
                id="three-setup-four-punch",
                title="三番四抖",
                category="technique",
                content="三番四抖是相声经典结构技巧。",
                summary="通过三次铺垫和一次转折制造笑点。",
                source="comedy_theory.md",
                entity_triples=[{"subject": "三番四抖", "relation": "属于", "object": "结构技巧"}],
                related_terms=["铺垫", "包袱", "转折"],
            ),
            KnowledgeItem(
                id="no-explain-joke",
                title="不要解释笑点",
                category="rule",
                content="笑点一旦被解释，笑果就会大打折扣。",
                summary="让笑点自然呈现，不要解释。",
                source="comedy_theory.md",
                entity_triples=[{"subject": "笑点", "relation": "不需要", "object": "解释"}],
                related_terms=["show don't tell", "自然呈现"],
            ),
        ]
        fake_llm = FakeLLM(fake_items)
        result = distill(sample_sections, llm=fake_llm)
        assert len(result) == 2
        assert all(isinstance(item, KnowledgeItem) for item in result)
        assert result[0].embedding_text, "embedding_text 应被自动填充"

    def test_distill_skips_invalid_category(self, sample_sections):
        # 使用 model_construct 绕过 Pydantic 校验，模拟 LLM 返回了非法类别
        fake_items = [
            KnowledgeItem.model_construct(
                id="bad",
                title="非法类别",
                category="invalid",
                content="...",
            )
        ]
        fake_llm = FakeLLM(fake_items)
        result = distill(sample_sections, llm=fake_llm)
        assert len(result) == 0

    def test_distill_empty_sections(self):
        fake_llm = FakeLLM([])
        result = distill([], llm=fake_llm)
        assert result == []


class TestSaveItems:
    """保存 JSONL 测试。"""

    def test_save_and_load(self, tmp_path):
        items = [
            KnowledgeItem(
                id="test-1",
                title="测试条目",
                category="concept",
                content="测试内容",
                summary="测试摘要",
                source="test.md",
                related_terms=["A", "B"],
            )
        ]
        output = tmp_path / "items.jsonl"
        save_items(items, output)

        lines = output.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["id"] == "test-1"
        assert data["category"] == "concept"
        assert "embedding_text" in data
