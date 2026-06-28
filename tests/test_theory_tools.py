"""测试喜剧理论知识工具函数。"""

import pytest

from comedy_agent.core.knowledge_models import KnowledgeItem
from comedy_agent.tools.theory_tools import (
    check_rule,
    get_pattern,
    list_techniques,
    query_theory,
)


@pytest.fixture
def sample_items():
    return [
        KnowledgeItem(
            id="three-setup-four-punch",
            title="三番四抖",
            category="technique",
            content="三番四抖是相声经典结构技巧。",
            summary="通过三次铺垫和一次转折制造笑点。",
            source="comedy_theory.md",
            related_terms=["铺垫", "包袱", "笑点"],
        ),
        KnowledgeItem(
            id="no-explain",
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
            content="建立、冲突升级、解决。",
            summary="三幕式结构。",
            source="sketch_structure.md",
        ),
    ]


class TestQueryTheory:
    """query_theory 测试。"""

    def test_query_theory_returns_formatted_text(self, monkeypatch, sample_items):
        monkeypatch.setattr(
            "comedy_agent.tools.theory_tools.retrieve_knowledge",
            lambda term, top_k: sample_items[:1],
        )
        result = query_theory("三番四抖")
        assert "三番四抖" in result
        assert "technique" in result
        assert "comedy_theory.md" in result

    def test_query_theory_empty(self, monkeypatch):
        monkeypatch.setattr(
            "comedy_agent.tools.theory_tools.retrieve_knowledge",
            lambda term, top_k: [],
        )
        result = query_theory("不存在")
        assert "未找到" in result


class TestListTechniques:
    """list_techniques 测试。"""

    def test_list_techniques_filters_category(self, monkeypatch, sample_items):
        monkeypatch.setattr(
            "comedy_agent.tools.theory_tools.retrieve_knowledge",
            lambda topic, category, top_k: [sample_items[0]],
        )
        result = list_techniques("结构")
        assert "三番四抖" in result
        assert "未找到" not in result


class TestGetPattern:
    """get_pattern 测试。"""

    def test_get_pattern_returns_pattern(self, monkeypatch, sample_items):
        monkeypatch.setattr(
            "comedy_agent.tools.theory_tools.retrieve_knowledge",
            lambda name, category, top_k: [sample_items[2]],
        )
        result = get_pattern("小品三幕结构")
        assert "小品三幕结构" in result
        assert "sketch_structure.md" in result


class TestCheckRule:
    """check_rule 测试。"""

    def test_check_rule_detects_violation(self, monkeypatch, sample_items):
        monkeypatch.setattr(
            "comedy_agent.tools.theory_tools.retrieve_knowledge",
            lambda query, category, top_k: [sample_items[1]],
        )
        result = check_rule("我来解释一下这个笑点是什么意思")
        assert "不要解释笑点" in result
        assert "可能违反" in result

    def test_check_rule_no_violation(self, monkeypatch, sample_items):
        monkeypatch.setattr(
            "comedy_agent.tools.theory_tools.retrieve_knowledge",
            lambda query, category, top_k: [sample_items[1]],
        )
        result = check_rule("今天天气真好")
        assert "未检测到明显违规" in result
