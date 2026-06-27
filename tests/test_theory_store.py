"""测试理论知识向量库存储。"""

import json
from pathlib import Path

import pytest

from comedy_agent.core.knowledge_models import KnowledgeItem
from comedy_agent.rag.theory_store import TheoryStore
from comedy_agent.rag.vector_store import VectorStore


@pytest.fixture
def sample_items() -> list[KnowledgeItem]:
    return [
        KnowledgeItem(
            id="three-setup-four-punch",
            title="三番四抖",
            category="technique",
            content="三番四抖是相声经典结构技巧。",
            summary="通过三次铺垫和一次转折制造笑点。",
            source="comedy_theory.md",
            entity_triples=[
                {"subject": "三番四抖", "relation": "属于", "object": "结构技巧"}
            ],
            related_terms=["铺垫", "包袱", "笑点"],
        ),
        KnowledgeItem(
            id="no-explain-joke",
            title="不要解释笑点",
            category="rule",
            content="笑点一旦被解释，笑果就会大打折扣。",
            summary="让笑点自然呈现。",
            source="comedy_theory.md",
            related_terms=["show don't tell", "自然呈现"],
        ),
        KnowledgeItem(
            id="sketch-three-act",
            title="小品三幕结构",
            category="pattern",
            content="小品通常采用三幕式结构。",
            summary="建立、冲突升级、解决。",
            source="sketch_structure.md",
            related_terms=["三幕式", "建立", "解决"],
        ),
    ]


@pytest.fixture
def theory_store(tmp_path: Path) -> TheoryStore:
    """每个测试使用独立的临时 Chroma 集合和本地 Embedding。"""
    vs = VectorStore(
        collection_name="test_theory",
        persist_path=str(tmp_path),
        embedding_model_name="hf-local",
    )
    return TheoryStore(vector_store=vs)


class TestTheoryStore:
    """TheoryStore 核心功能测试。"""

    def test_ingest_and_count(self, theory_store, sample_items):
        ids = theory_store.ingest(sample_items)
        assert len(ids) == len(sample_items)
        assert theory_store.count() == len(sample_items)

    def test_search_returns_relevant_items(self, theory_store, sample_items):
        theory_store.ingest(sample_items)
        results = theory_store.search("三番四抖", top_k=2)
        assert len(results) <= 2
        assert any("三番四抖" in r.title for r in results)

    def test_search_filter_by_category(self, theory_store, sample_items):
        theory_store.ingest(sample_items)
        results = theory_store.search("铺垫", category="technique", top_k=5)
        assert len(results) >= 1
        assert all(r.category == "technique" for r in results)

    def test_get_by_id(self, theory_store, sample_items):
        theory_store.ingest(sample_items)
        item = theory_store.get_by_id("no-explain-joke")
        assert item is not None
        assert item.title == "不要解释笑点"

    def test_round_trip_preserves_fields(self, theory_store, sample_items):
        theory_store.ingest(sample_items)
        item = theory_store.get_by_id("three-setup-four-punch")
        assert item is not None
        assert item.category == "technique"
        assert item.source == "comedy_theory.md"
        assert len(item.entity_triples) >= 1
        assert any(t.subject == "三番四抖" for t in item.entity_triples)

    def test_clear(self, theory_store, sample_items):
        theory_store.ingest(sample_items)
        assert theory_store.count() == len(sample_items)
        theory_store.clear()
        assert theory_store.count() == 0


class TestIngestTheoryScript:
    """scripts/ingest_theory.py 集成测试。"""

    def test_load_items_from_jsonl(self, tmp_path: Path):
        from scripts.ingest_theory import load_items

        jsonl = tmp_path / "items.jsonl"
        items = [
            KnowledgeItem(id="a", title="A", category="concept", content="..."),
            KnowledgeItem(id="b", title="B", category="rule", content="..."),
        ]
        with jsonl.open("w", encoding="utf-8") as f:
            for item in items:
                f.write(item.model_dump_json(ensure_ascii=False) + "\n")

        loaded = load_items(jsonl)
        assert len(loaded) == 2
        assert loaded[0].id == "a"
