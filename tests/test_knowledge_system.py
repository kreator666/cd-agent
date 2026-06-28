"""测试知识系统统一检索接口。"""

from pathlib import Path

import pytest

from comedy_agent.core.knowledge_models import KnowledgeItem
from comedy_agent.core.knowledge_system import (
    KnowledgeSystem,
    _keyword_search,
    _rrf_fuse,
    _tokenize,
    retrieve_knowledge,
)
from comedy_agent.rag.theory_store import TheoryStore


class TestTokenizer:
    """分词工具测试。"""

    def test_tokenize_english_and_chinese(self):
        tokens = _tokenize("三番四抖 setup-punch")
        # 当前分词把每个中文字符视为一个 token
        assert "三" in tokens
        assert "番" in tokens
        assert "四" in tokens
        assert "抖" in tokens
        assert "setup-punch" in tokens

    def test_tokenize_deduplicates(self):
        tokens = _tokenize("铺垫 铺垫 铺垫")
        assert len(tokens) == 2
        assert "铺" in tokens
        assert "垫" in tokens


class TestKeywordSearch:
    """关键词检索测试。"""

    def test_keyword_search_basic(self):
        items = [
            KnowledgeItem(
                id="a",
                title="三番四抖",
                category="technique",
                content="铺垫铺垫铺垫，抖包袱。",
            ),
            KnowledgeItem(
                id="b",
                title="不要解释笑点",
                category="rule",
                content="show don't tell。",
            ),
        ]
        results = _keyword_search("铺垫", items, top_k=5)
        assert len(results) == 1
        assert results[0][0] == "a"

    def test_keyword_search_filter_category(self):
        items = [
            KnowledgeItem(id="a", title="A", category="technique", content="铺垫"),
            KnowledgeItem(id="b", title="B", category="rule", content="铺垫"),
        ]
        results = _keyword_search("铺垫", items, category="rule", top_k=5)
        assert len(results) == 1
        assert results[0][0] == "b"


class TestRRFFusion:
    """RRF 融合测试。"""

    def test_rrf_combines_vector_and_keyword(self):
        vector_items = [
            KnowledgeItem(id="a", title="A", category="concept", content="..."),
            KnowledgeItem(id="b", title="B", category="concept", content="..."),
        ]
        keyword_results = [("b", 1.0), ("c", 0.9)]
        keyword_item_by_id = {
            "c": KnowledgeItem(id="c", title="C", category="concept", content="..."),
        }
        fused = _rrf_fuse(vector_items, keyword_results, keyword_item_by_id)
        # b 在两条路径都出现，应该排第一
        assert fused[0][1] == "b"

    def test_rrf_includes_keyword_only_items(self):
        vector_items = [
            KnowledgeItem(id="a", title="A", category="concept", content="..."),
        ]
        keyword_results = [("a", 1.0), ("ghost", 0.9)]
        keyword_item_by_id = {
            "ghost": KnowledgeItem(
                id="ghost", title="Ghost", category="concept", content="..."
            ),
        }
        fused = _rrf_fuse(vector_items, keyword_results, keyword_item_by_id)
        ghost_entry = next((x for x in fused if x[1] == "ghost"), None)
        assert ghost_entry is not None
        assert ghost_entry[2] is not None
        assert ghost_entry[2].id == "ghost"


class FakeTheoryStore:
    """用于单元测试的 TheoryStore 替身。"""

    def __init__(self, items):
        self._items = items

    def search(self, query, category=None, top_k=5):
        results = []
        for item in self._items:
            if category and item.category != category:
                continue
            if any(tok in item.build_embedding_text() for tok in _tokenize(query)):
                results.append(item)
            if len(results) >= top_k:
                break
        return results


class TestKnowledgeSystem:
    """KnowledgeSystem 检索测试。"""

    @pytest.fixture
    def sample_items(self):
        return [
            KnowledgeItem(
                id="three-setup-four-punch",
                title="三番四抖",
                category="technique",
                content="三番四抖是相声经典结构技巧。",
                related_terms=["铺垫", "包袱"],
            ),
            KnowledgeItem(
                id="callback",
                title="Callback",
                category="technique",
                content="Callback 是回扣前面笑点。",
                related_terms=["伏笔", "回扣"],
            ),
            KnowledgeItem(
                id="no-explain",
                title="不要解释笑点",
                category="rule",
                content="不要解释笑点。",
            ),
        ]

    def test_retrieve_returns_items(self, sample_items, tmp_path: Path):
        fake_store = FakeTheoryStore(sample_items)
        system = KnowledgeSystem(
            theory_store=fake_store,  # type: ignore[arg-type]
            keyword_corpus_path=tmp_path / "empty.jsonl",
        )
        results = system.retrieve("三番四抖", top_k=5)
        assert len(results) >= 1
        assert any(r.id == "three-setup-four-punch" for r in results)

    def test_retrieve_filter_category(self, sample_items, tmp_path: Path):
        fake_store = FakeTheoryStore(sample_items)
        system = KnowledgeSystem(
            theory_store=fake_store,  # type: ignore[arg-type]
            keyword_corpus_path=tmp_path / "empty.jsonl",
        )
        results = system.retrieve("技巧", category="technique", top_k=5)
        assert all(r.category == "technique" for r in results)

    def test_retrieve_keyword_fallback_when_vector_empty(self, tmp_path: Path):
        """向量检索无结果时，关键词检索应返回结果。"""
        from comedy_agent.core.knowledge_system import _load_keyword_index

        items = [
            KnowledgeItem(
                id="x",
                title="预期违背",
                category="technique",
                content="预期违背是喜剧底层机制。",
                related_terms=["反转", "预期"],
            )
        ]
        # 向量库故意为空
        fake_store = FakeTheoryStore([])
        # 写临时关键词索引
        corpus = tmp_path / "items.jsonl"
        with corpus.open("w", encoding="utf-8") as f:
            for item in items:
                f.write(item.model_dump_json(ensure_ascii=False) + "\n")

        # 清空 lru_cache，确保加载临时文件
        _load_keyword_index.cache_clear()
        system = KnowledgeSystem(
            theory_store=fake_store,  # type: ignore[arg-type]
            keyword_corpus_path=corpus,
        )
        results = system.retrieve("预期违背", top_k=5)
        assert len(results) >= 1
        assert results[0].id == "x"
        _load_keyword_index.cache_clear()

    def test_retrieve_knowledge_module_function(self, tmp_path: Path):
        items = [
            KnowledgeItem(id="a", title="A", category="concept", content="AAA")
        ]
        corpus = tmp_path / "items.jsonl"
        with corpus.open("w", encoding="utf-8") as f:
            for item in items:
                f.write(item.model_dump_json(ensure_ascii=False) + "\n")

        from comedy_agent.core.knowledge_system import _load_keyword_index

        _load_keyword_index.cache_clear()
        fake_store = FakeTheoryStore([])
        results = retrieve_knowledge(
            "AAA",
            top_k=5,
            theory_store=fake_store,  # type: ignore[arg-type]
            keyword_corpus_path=corpus,
        )
        assert len(results) >= 1
        _load_keyword_index.cache_clear()


class TestKnowledgeSystemIntegration:
    """使用真实 TheoryStore 的集成测试（可选，依赖本地 Embedding）。"""

    def test_real_retrieve_from_comedy_theory(self, tmp_path: Path):
        from comedy_agent.rag.vector_store import VectorStore

        vs = VectorStore(
            collection_name="test_knowledge_system",
            persist_path=str(tmp_path),
            embedding_model_name="hf-local",
        )
        store = TheoryStore(vector_store=vs)
        items = [
            KnowledgeItem(
                id="three-setup-four-punch",
                title="三番四抖",
                category="technique",
                content="三番四抖是相声经典结构技巧。",
                related_terms=["铺垫", "包袱"],
            ),
            KnowledgeItem(
                id="no-explain",
                title="不要解释笑点",
                category="rule",
                content="不要解释笑点。",
            ),
        ]
        store.ingest(items)
        system = KnowledgeSystem(theory_store=store)
        results = system.retrieve("三番四抖", top_k=2)
        assert any(r.id == "three-setup-four-punch" for r in results)
