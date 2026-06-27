"""示例检索器测试。"""

from unittest.mock import MagicMock

import pytest

from comedy_agent.core.annotation import AnnotatedExample
from comedy_agent.core.example_retriever import (
    _compute_score,
    _document_to_example,
    retrieve_examples,
)
from langchain_core.documents import Document


def _make_doc(
    doc_id: str,
    content: str,
    distance: float = 0.2,
    style: str = "",
    structure_type: str = "",
    humor_score: float = 5,
    topic: str = "",
) -> Document:
    return Document(
        page_content=content,
        metadata={
            "doc_id": doc_id,
            "distance": distance,
            "style": style,
            "structure_type": structure_type,
            "humor_score": humor_score,
            "topic": topic,
            "content": content,
        },
    )


class TestComputeScore:
    def test_style_match_boosts_score(self):
        doc = _make_doc("1", "x", distance=0.2, style="自嘲")
        score_match = _compute_score(doc, target_style="自嘲", target_structure=None)
        score_mismatch = _compute_score(doc, target_style="观察", target_structure=None)
        assert score_match > score_mismatch

    def test_structure_match_boosts_score(self):
        doc = _make_doc("1", "x", distance=0.2, structure_type="story")
        score_match = _compute_score(doc, target_style=None, target_structure="story")
        score_mismatch = _compute_score(doc, target_style=None, target_structure="one_liner")
        assert score_match > score_mismatch

    def test_humor_score_bonus(self):
        doc_high = _make_doc("1", "x", distance=0.2, humor_score=9)
        doc_low = _make_doc("2", "x", distance=0.2, humor_score=3)
        assert _compute_score(doc_high, None, None) > _compute_score(doc_low, None, None)


class TestDocumentToExample:
    def test_converts_document_to_example(self):
        doc = _make_doc("id-1", "content text", style="自嘲", topic="上班")
        ex = _document_to_example(doc)
        assert ex.example_id == "id-1"
        assert ex.content == "content text"
        assert ex.style == "自嘲"


class TestRetrieveExamples:
    def test_retrieve_top_k_and_sort(self):
        store = MagicMock()
        store.collection_name = "mock"
        store.search.return_value = [
            _make_doc("1", "A", distance=0.1, style="自嘲"),
            _make_doc("2", "B", distance=0.5, style="观察"),
            _make_doc("3", "C", distance=0.2, style="自嘲"),
        ]

        examples = retrieve_examples(
            "上班自嘲",
            top_k=2,
            style="自嘲",
            vector_stores=[store],
        )

        assert len(examples) == 2
        # 风格匹配且距离更小的应排在前面
        assert examples[0].example_id == "1"
        assert examples[1].example_id == "3"

    def test_deduplicate_across_stores(self):
        store_a = MagicMock()
        store_a.collection_name = "a"
        store_a.search.return_value = [_make_doc("1", "A", distance=0.1)]
        store_b = MagicMock()
        store_b.collection_name = "b"
        store_b.search.return_value = [_make_doc("1", "A", distance=0.2)]

        examples = retrieve_examples(
            "query",
            top_k=5,
            vector_stores=[store_a, store_b],
        )
        assert len(examples) == 1
