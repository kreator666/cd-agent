"""测试喜剧行业特殊优化 —— 结构感知分块与多向量表示。"""

from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.documents import Document

from comedy_agent.rag.comedy_optimizer import ComedyChunker, MultiVectorStore


class TestComedyChunkerDetect:
    """ComedyChunker 自动检测测试。"""

    def test_detect_structure_script(self):
        text = "第一场 客厅\n郭德纲：大家好。\n于谦：好。"
        assert ComedyChunker.detect_structure_type(text) == "script"

    def test_detect_structure_theory(self):
        text = "## 理论\n三番四抖是相声的经典结构。"
        assert ComedyChunker.detect_structure_type(text) == "theory"

    def test_detect_structure_tutorial(self):
        text = "步骤1：观察生活\n步骤2：找到笑点"
        assert ComedyChunker.detect_structure_type(text) == "tutorial"

    def test_detect_structure_analysis(self):
        text = "分析这段相声的优点：节奏好、包袱响。"
        assert ComedyChunker.detect_structure_type(text) == "analysis"

    def test_detect_structure_unknown(self):
        text = "这是一段普通文本，没有明显结构标记。"
        assert ComedyChunker.detect_structure_type(text) == "unknown"

    def test_detect_style_observational(self):
        text = "观察式喜剧需要关注身边的日常小事。"
        assert ComedyChunker.detect_style_type(text) == "observational"

    def test_detect_style_satire(self):
        text = "讽刺喜剧揭露社会现象的荒谬本质。"
        assert ComedyChunker.detect_style_type(text) == "satire"

    def test_detect_style_unknown(self):
        text = "今天天气不错。"
        assert ComedyChunker.detect_style_type(text) == "unknown"

    def test_has_punchline(self):
        assert ComedyChunker.has_punchline("他说完，（笑声）全场爆笑。")
        assert not ComedyChunker.has_punchline("这是一段普通叙述。")

    def test_extract_scene_title(self):
        text = "第一场 客厅\n角色A：你好。"
        assert ComedyChunker.extract_scene_title(text) == "第一场 客厅"

    def test_extract_scene_title_bracket(self):
        text = "【场景：餐厅】\n角色B：吃饭了吗？"
        assert ComedyChunker.extract_scene_title(text) == "【场景：餐厅】"

    def test_extract_scene_title_none(self):
        assert ComedyChunker.extract_scene_title("普通文本") is None


class TestComedyChunkerEnrich:
    """元数据 enriched 测试。"""

    def test_enrich_metadata(self):
        docs = [
            Document(page_content="第一场\n郭德纲：你好。", metadata={"source": "test"}),
        ]
        enriched = ComedyChunker.enrich_metadata(docs)
        assert enriched[0].metadata["structure_type"] == "script"
        assert enriched[0].metadata["has_punchline"] is False
        assert enriched[0].metadata["scene_title"] == "第一场"
        assert "style_type" in enriched[0].metadata

    def test_enrich_preserves_existing(self):
        docs = [Document(page_content="理论内容。", metadata={"custom": 123})]
        enriched = ComedyChunker.enrich_metadata(docs)
        assert enriched[0].metadata["custom"] == 123


class TestComedyChunkerSplitByPunchlineUnit:
    """笑点单元分块测试。"""

    def test_short_text_no_split(self):
        docs = [Document(page_content="短文本。", metadata={})]
        result = ComedyChunker.split_by_punchline_unit(docs, max_chunk_size=1000)
        assert len(result) == 1
        assert result[0].metadata["strategy"] == "punchline_unit"
        assert result[0].metadata["structure_type"] == "unknown"

    def test_long_text_split(self):
        text = "这是一句。" * 200  # ~1000 chars
        docs = [Document(page_content=text, metadata={})]
        result = ComedyChunker.split_by_punchline_unit(docs, max_chunk_size=300)
        assert len(result) > 1
        for r in result:
            assert "strategy" in r.metadata

    def test_punchline_detected_in_chunk(self):
        text = "铺垫内容。他说完，（笑声）全场爆笑。"
        docs = [Document(page_content=text, metadata={})]
        result = ComedyChunker.split_by_punchline_unit(docs)
        assert result[0].metadata["has_punchline"] is True


class TestMultiVectorStore:
    """多向量存储测试。"""

    @pytest.fixture
    def mvs(self, tmp_path: Path):
        with patch(
            "comedy_agent.rag.vector_store.ModelFactory.get_embedding_model",
            return_value=_FakeEmbeddings(),
        ):
            return MultiVectorStore(
                base_collection_name="test_multi",
                persist_path=str(tmp_path / "chroma_multi"),
            )

    def test_add_and_search_content(self, mvs: MultiVectorStore):
        docs = [
            Document(page_content="相声理论", metadata={"structure_type": "theory"}),
            Document(page_content="小品剧本", metadata={"structure_type": "script"}),
        ]
        ids = mvs.add_documents(docs, vector_types=["content"])
        assert "content" in ids
        assert len(ids["content"]) == 2

        results = mvs.search("相声", vector_types=["content"], top_k=2)
        assert len(results) >= 1

    def test_add_multiple_types(self, mvs: MultiVectorStore):
        docs = [Document(page_content="测试文档", metadata={})]
        ids = mvs.add_documents(docs, vector_types=["content", "structure"])
        assert "content" in ids
        assert "structure" in ids

    def test_search_cross_types(self, mvs: MultiVectorStore):
        docs = [Document(page_content="跨类型测试", metadata={})]
        mvs.add_documents(docs, vector_types=["content", "style"])

        results = mvs.search("跨类型", vector_types=["content", "style"], top_k=5)
        assert len(results) >= 1
        # 去重后应只有 1 条，但标记了多个 vector_type
        assert "vector_type" in results[0].metadata

    def test_search_by_structure(self, mvs: MultiVectorStore):
        docs = [
            Document(page_content="理论A", metadata={"structure_type": "theory"}),
            Document(page_content="剧本B", metadata={"structure_type": "script"}),
        ]
        mvs.add_documents(docs, vector_types=["content"])

        results = mvs.search_by_structure("内容", structure_type="theory", top_k=5)
        assert len(results) == 1
        assert results[0].metadata["structure_type"] == "theory"

    def test_search_by_style(self, mvs: MultiVectorStore):
        docs = [
            Document(page_content="讽刺内容", metadata={"style_type": "satire"}),
            Document(page_content="荒诞内容", metadata={"style_type": "absurd"}),
        ]
        mvs.add_documents(docs, vector_types=["content"])

        results = mvs.search_by_style("内容", style_type="satire", top_k=5)
        assert len(results) == 1
        assert results[0].metadata["style_type"] == "satire"

    def test_count_and_clear(self, mvs: MultiVectorStore):
        docs = [Document(page_content="计数测试", metadata={})]
        mvs.add_documents(docs, vector_types=["content"])
        assert mvs.count("content") == 1

        mvs.clear("content")
        assert mvs.count("content") == 0

    def test_invalid_vector_type(self, mvs: MultiVectorStore):
        docs = [Document(page_content="x", metadata={})]
        with pytest.raises(ValueError, match="未知向量类型"):
            mvs.add_documents(docs, vector_types=["invalid"])


class _FakeEmbeddings:
    """用于测试的假 Embedding 模型。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] * 10 for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))] * 10
