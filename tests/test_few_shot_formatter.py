"""Few-shot 格式化器测试。"""

from langchain_core.documents import Document

from comedy_agent.core.annotation import AnnotatedExample
from comedy_agent.core.few_shot_formatter import format_examples


class TestFormatExamples:
    def test_empty_returns_empty(self):
        assert format_examples([]) == ""

    def test_format_annotated_examples(self):
        examples = [
            AnnotatedExample(
                content="完整文本",
                setup="铺垫",
                punchline="笑点",
                topic="上班",
                style="自嘲",
                tags=["职场", "加班"],
            )
        ]
        text = format_examples(examples)
        assert "【参考示例】" in text
        assert "示例 1:" in text
        assert "话题：上班" in text
        assert "风格：自嘲" in text
        assert "铺垫：铺垫" in text
        assert "笑点：笑点" in text

    def test_format_documents(self):
        docs = [
            Document(
                page_content="文本内容",
                metadata={"topic": "相亲", "style": "观察", "setup": "铺垫", "punchline": "笑点"},
            )
        ]
        text = format_examples(docs)
        assert "示例 1:" in text
        assert "话题：相亲" in text

    def test_fallback_to_content(self):
        examples = [AnnotatedExample(content="只有完整文本")]
        text = format_examples(examples)
        assert "文本：只有完整文本" in text
        assert "铺垫" not in text

    def test_token_budget_truncation(self):
        examples = [
            AnnotatedExample(content="A" * 100, setup="S", punchline="P", topic="话题", style="风格"),
            AnnotatedExample(content="B" * 100, setup="S", punchline="P", topic="话题", style="风格"),
        ]
        text = format_examples(examples, max_tokens=15)
        # 15 tokens ≈ 10 字符，只能保留第一条
        assert "示例 1:" in text
        assert "示例 2:" not in text
