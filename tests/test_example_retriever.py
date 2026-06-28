"""示例检索器测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from comedy_agent.core.example_retriever import retrieve_examples


def test_retrieve_examples_returns_annotated_examples():
    """验证 retrieve_examples 能把 Document 还原为 AnnotatedExample。"""
    fake_doc = Document(
        page_content="话题：加班\n风格：吐槽\n结构：dialogue\n标签：加班/职场/吐槽\n铺垫：公司加班文化浓\n笑点：等我们都走完，他好一个人静静\n文本：示例文本",
        metadata={
            "doc_id": "ex-004",
            "content": "示例文本",
            "setup": "公司加班文化浓",
            "punchline": "等我们都走完，他好一个人静静",
            "callback": False,
            "callback_to": None,
            "tags": ["加班", "职场", "吐槽"],
            "topic": "加班",
            "style": "吐槽",
            "kind": "standup",
            "structure_type": "dialogue",
            "humor_score": 7,
            "source": "test",
            "distance": 0.1,
        },
    )
    fake_store = MagicMock()
    fake_store.collection_name = "comedy_knowledge"
    fake_store.search.return_value = [fake_doc]

    with patch(
        "comedy_agent.core.example_retriever._get_vector_stores",
        return_value=[fake_store],
    ):
        examples = retrieve_examples("加班", top_k=3, kind="standup", style="吐槽")

    assert len(examples) == 1
    ex = examples[0]
    assert ex.example_id == "ex-004"
    assert ex.topic == "加班"
    assert ex.style == "吐槽"
    assert "示例文本" in ex.content


def test_retrieve_examples_no_candidates():
    """空库时返回空列表，不抛异常。"""
    fake_store = MagicMock()
    fake_store.collection_name = "comedy_knowledge"
    fake_store.search.return_value = []

    with patch(
        "comedy_agent.core.example_retriever._get_vector_stores",
        return_value=[fake_store],
    ):
        examples = retrieve_examples("不存在的话题", top_k=3)

    assert examples == []
