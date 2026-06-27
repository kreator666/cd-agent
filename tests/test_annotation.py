"""标注流水线测试。"""

import json
import tempfile
from pathlib import Path

import pytest

from comedy_agent.core.annotation import (
    AnnotatedExample,
    annotate_text,
    build_embedding_text,
    generate_schema_json,
    load_raw_segments,
    process_texts,
    save_annotations,
    split_text_into_segments,
)
from tests.conftest import make_structured_mock_llm


class TestAnnotatedExample:
    def test_schema_generation(self):
        schema = generate_schema_json()
        assert schema["title"] == "AnnotatedExample"
        assert "content" in schema["properties"]
        assert "setup" in schema["properties"]
        assert "punchline" in schema["properties"]
        assert "humor_score" in schema["properties"]

    def test_tags_normalization(self):
        ex = AnnotatedExample(content="x", tags="职场, 加班, 自嘲")
        assert ex.tags == ["职场", "加班", "自嘲"]

    def test_embedding_text(self):
        ex = AnnotatedExample(
            content="测试文本",
            topic="测试",
            style="自嘲",
            setup="铺垫",
            punchline="笑点",
            tags=["a", "b"],
        )
        text = build_embedding_text(ex)
        assert "话题：测试" in text
        assert "风格：自嘲" in text
        assert "铺垫：铺垫" in text
        assert "笑点：笑点" in text


class TestSegmentation:
    def test_split_by_blank_lines(self):
        text = "这是一个足够长的第一段文本。\n\n这是第二段文本，也有足够长度。\n\n\n这是第三段文本，同样不短。"
        segments = split_text_into_segments(text)
        assert len(segments) == 3

    def test_ignore_short_segments(self):
        text = "这是一个有效的长段落。\n\nhi"
        segments = split_text_into_segments(text)
        assert len(segments) == 1
        assert "有效" in segments[0]


class TestAnnotateText:
    def test_annotate_text_with_mock_llm(self):
        llm = make_structured_mock_llm(
            responses={
                AnnotatedExample: AnnotatedExample(
                    content="mocked",
                    setup="铺垫",
                    punchline="笑点",
                    tags=["职场"],
                    topic="上班",
                    style="自嘲",
                    humor_score=7,
                )
            }
        )
        ex = annotate_text("我今天上班迟到了。", llm=llm, kind="standup", source="test")
        assert ex.content == "我今天上班迟到了。"
        assert ex.setup == "铺垫"
        assert ex.punchline == "笑点"
        assert ex.kind == "standup"
        assert ex.source == "test"
        assert ex.embedding_text != ""

    def test_annotate_text_fallback_on_error(self):
        llm = make_structured_mock_llm()
        # 默认 mock 的 with_structured_output 返回空 MagicMock，会触发回退
        ex = annotate_text("fallback text", llm=llm)
        assert ex.content == "fallback text"
        assert ex.kind == "standup"


class TestProcessAndSave:
    def test_process_texts(self):
        llm = make_structured_mock_llm(
            responses={
                AnnotatedExample: AnnotatedExample(
                    content="mocked",
                    setup="铺垫",
                    punchline="笑点",
                    topic="测试",
                    style="自嘲",
                    humor_score=6,
                )
            }
        )
        examples = process_texts(["文本一", "文本二"], llm=llm, kind="standup")
        assert len(examples) == 2
        assert examples[0].topic == "测试"

    def test_load_raw_segments_txt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "jokes.txt"
            path.write_text("这是第一个足够长的段子。\n\n这是第二个足够长的段子。", encoding="utf-8")
            segments = load_raw_segments(path)
            assert len(segments) == 2

    def test_load_raw_segments_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "jokes.jsonl"
            path.write_text(
                '{"content":"这是一个足够长的段子一"}\n{"text":"这是另一个足够长的段子二"}\n',
                encoding="utf-8",
            )
            segments = load_raw_segments(path)
            assert len(segments) == 2

    def test_save_annotations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "out.jsonl"
            examples = [
                AnnotatedExample(content="A", setup="s", punchline="p"),
                AnnotatedExample(content="B", setup="s", punchline="p"),
            ]
            save_annotations(examples, output)
            lines = output.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 2
            data = json.loads(lines[0])
            assert data["content"] == "A"
