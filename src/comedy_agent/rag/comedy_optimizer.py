"""喜剧行业特殊优化 —— 结构感知分块与多向量表示。

提供喜剧文本专用的结构感知分块、元数据自动 enriched，以及
基于同一 Embedding 模型的多向量类型存储与检索（content / structure / style）。
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from langchain_core.documents import Document

from comedy_agent.rag.chunker import DocumentChunker
from comedy_agent.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# 结构/风格检测正则
# ------------------------------------------------------------------ #

# 剧本类标记
_SCRIPT_MARKERS = [
    re.compile(r"第[一二三四五六七八九十百零\d]+场"),
    re.compile(r"[\u4e00-\u9fa5]{1,8}[甲乙丙丁]?[：:]"),  # 角色对话
    re.compile(r"【.*?】"),  # 舞台说明
]

# 理论类标记
_THEORY_MARKERS = [
    re.compile(r"##?\s*(理论|技巧|方法|原则|定义|结构)"),
    re.compile(r"(核心|关键|要点|总结)\s*[:：]"),
]

# 教程类标记
_TUTORIAL_MARKERS = [
    re.compile(r"(步骤|Step|阶段|流程)\s*\d*"),
    re.compile(r"##?\s*(入门|基础|进阶|实战)"),
]

# 分析类标记
_ANALYSIS_MARKERS = [
    re.compile(r"(分析|评估|评价|拆解|诊断)"),
    re.compile(r"(优点|缺点|问题|建议|改进)\s*[:：]"),
]

# 喜剧风格标记
_STYLE_MARKERS: dict[str, list[re.Pattern]] = {
    "observational": [re.compile(r"(观察|日常|生活|身边)"), re.compile(r"你会发现")],
    "satire": [re.compile(r"(讽刺|批判|社会|现象|问题)"), re.compile(r"本质上")],
    "black_humor": [re.compile(r"(黑色|荒诞|死亡|悲剧)"), re.compile(r"(笑.*哭|哭.*笑)")],
    "absurd": [re.compile(r"(无厘头|荒诞|莫名其妙|逻辑)"), re.compile(r"(其实.*没有|没有.*其实)")],
    "wordplay": [re.compile(r"(谐音|双关|文字|梗)"), re.compile(r"(听起来|说起来)")],
}

# 笑点标记
_PUNCHLINE_PATTERNS = [
    re.compile(r"[。！？，、]\s*（笑声?|掌声|大笑|爆笑|效果）"),
    re.compile(r"[。！？，、]\s*\(笑声?\)"),
    re.compile(r"包袱[:：]"),
    re.compile(r"笑点[:：]"),
]


# ------------------------------------------------------------------ #
# ComedyChunker —— 结构感知分块
# ------------------------------------------------------------------ #


class ComedyChunker:
    """喜剧行业专用结构感知分块器。

    在通用分块器基础上，增加对喜剧文本结构的识别与 enriched：
    - 自动检测文本结构类型（理论 / 剧本 / 教程 / 分析）
    - 自动检测喜剧风格（观察式 / 讽刺 / 黑色幽默 / 荒诞 / 文字游戏）
    - 按"笑点单元"分块（确保铺垫+包袱不被拆分）
    - 标记是否包含笑点 / 场景信息
    """

    # ------------------------------------------------------------------ #
    # 结构感知分块
    # ------------------------------------------------------------------ #
    @classmethod
    def split_by_punchline_unit(
        cls,
        documents: list[Document],
        max_chunk_size: int = 1200,
    ) -> list[Document]:
        """按笑点单元分块。

        识别文本中的"铺垫 -> 包袱"完整结构，尽量确保一个笑点单元
        不会被拆分到不同 chunk 中。如果单元过长，则在句子边界处拆分。

        Args:
            documents: 输入文档列表。
            max_chunk_size: 单块最大字符数。

        Returns:
            list[Document]: 分块后的文档列表，metadata  enriched 结构信息。
        """
        result: list[Document] = []
        for doc in documents:
            text = doc.page_content
            if len(text) <= max_chunk_size:
                meta = {
                    **doc.metadata,
                    "strategy": "punchline_unit",
                }
                meta = cls._enrich_single(meta, text)
                result.append(Document(page_content=text, metadata=meta))
                continue

            # 按句子拆分文本
            sentences = cls._split_to_sentences(text)
            current_chunk: list[str] = []
            current_len = 0
            chunk_idx = 0

            for sent in sentences:
                sent_len = len(sent)
                # 如果加入当前句子会超出限制，且当前块已有内容，则先 flush
                if current_len + sent_len > max_chunk_size and current_chunk:
                    chunk_text = "".join(current_chunk).strip()
                    meta = {
                        **doc.metadata,
                        "chunk_index": chunk_idx,
                        "strategy": "punchline_unit",
                    }
                    meta = cls._enrich_single(meta, chunk_text)
                    result.append(Document(page_content=chunk_text, metadata=meta))
                    chunk_idx += 1
                    current_chunk = [sent]
                    current_len = sent_len
                else:
                    current_chunk.append(sent)
                    current_len += sent_len

            # flush 最后一块
            if current_chunk:
                chunk_text = "".join(current_chunk).strip()
                meta = {
                    **doc.metadata,
                    "chunk_index": chunk_idx,
                    "strategy": "punchline_unit",
                }
                meta = cls._enrich_single(meta, chunk_text)
                result.append(Document(page_content=chunk_text, metadata=meta))

        return result

    @classmethod
    def enrich_metadata(cls, documents: list[Document]) -> list[Document]:
        """为文档批量 enriched 喜剧行业元数据。

        Args:
            documents: 输入文档列表。

        Returns:
            list[Document]:  enriched 后的文档列表。
        """
        return [
            Document(
                page_content=doc.page_content,
                metadata=cls._enrich_single(doc.metadata, doc.page_content),
            )
            for doc in documents
        ]

    # ------------------------------------------------------------------ #
    # 自动检测
    # ------------------------------------------------------------------ #
    @classmethod
    def detect_structure_type(cls, text: str) -> str:
        """自动检测文本结构类型。

        Returns:
            str: ``theory`` / ``script`` / ``tutorial`` / ``analysis`` / ``unknown``
        """
        scores = {
            "script": sum(1 for p in _SCRIPT_MARKERS if p.search(text)),
            "theory": sum(1 for p in _THEORY_MARKERS if p.search(text)),
            "tutorial": sum(1 for p in _TUTORIAL_MARKERS if p.search(text)),
            "analysis": sum(1 for p in _ANALYSIS_MARKERS if p.search(text)),
        }
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "unknown"

    @classmethod
    def detect_style_type(cls, text: str) -> str:
        """自动检测喜剧风格类型。

        Returns:
            str: ``observational`` / ``satire`` / ``black_humor`` /
                 ``absurd`` / ``wordplay`` / ``unknown``
        """
        scores: dict[str, int] = {}
        for style, patterns in _STYLE_MARKERS.items():
            scores[style] = sum(1 for p in patterns if p.search(text))
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "unknown"

    @classmethod
    def has_punchline(cls, text: str) -> bool:
        """判断文本是否包含明显的笑点标记。"""
        return any(p.search(text) for p in _PUNCHLINE_PATTERNS)

    @classmethod
    def extract_scene_title(cls, text: str) -> str | None:
        """从文本中提取场景标题（如"第一场 客厅"）。"""
        m = re.search(r"(第[一二三四五六七八九十百零\d]+场[^\n]*)", text)
        if m:
            return m.group(1).strip()
        m = re.search(r"(【场景[^】]*】)", text)
        if m:
            return m.group(1).strip()
        return None

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _split_to_sentences(text: str) -> list[str]:
        """按中文/英文句子边界拆分文本。"""
        # 在中文标点或换行处拆分，但保留标点
        parts = re.split(r"([。！？\n；])", text)
        sentences: list[str] = []
        i = 0
        while i < len(parts):
            s = parts[i]
            # 如果下一个是标点，合并进来
            if i + 1 < len(parts) and parts[i + 1] in "。！？\n；":
                s += parts[i + 1]
                i += 2
            else:
                i += 1
            if s.strip():
                sentences.append(s)
        return sentences

    @classmethod
    def _enrich_single(cls, meta: dict[str, Any], text: str) -> dict[str, Any]:
        """为单个文档 enriched 元数据。"""
        enriched = dict(meta)
        enriched["structure_type"] = cls.detect_structure_type(text)
        enriched["style_type"] = cls.detect_style_type(text)
        enriched["has_punchline"] = cls.has_punchline(text)
        scene = cls.extract_scene_title(text)
        if scene:
            enriched["scene_title"] = scene
        return enriched

    # ------------------------------------------------------------------ #
    # 多向量文本生成
    # ------------------------------------------------------------------ #
    @classmethod
    def generate_vector_texts(cls, doc: Document) -> dict[str, str]:
        """为 Document 生成三种向量表示文本。

        基于喜剧行业特征，为同一 chunk 生成内容/结构/风格三种语义视角的文本，
        分别用于生成不同的 Embedding 向量，提升检索精度。

        Args:
            doc: 输入文档。

        Returns:
            dict: {"content": 原始文本, "structure": 结构摘要, "style": 风格摘要}
        """
        content = doc.page_content
        meta = doc.metadata

        # 复用已有 metadata，避免重复检测
        structure_type = meta.get("structure_type") or cls.detect_structure_type(content)
        style_type = meta.get("style_type") or cls.detect_style_type(content)
        has_punchline = meta.get("has_punchline")
        if has_punchline is None:
            has_punchline = cls.has_punchline(content)
        scene_title = meta.get("scene_title") or cls.extract_scene_title(content)

        # content: 原始文本
        # structure: 结构特征摘要
        structure_parts = [f"这是一段{structure_type}类型的喜剧文本。"]
        if scene_title:
            structure_parts.append(f"场景：{scene_title}。")
        if has_punchline:
            structure_parts.append("包含笑点或包袱。")
        roles = cls._extract_roles(content)
        if roles:
            structure_parts.append(f"角色：{'、'.join(roles)}。")
        # 追加内容前 80 字作为摘要
        summary = content[:80].replace("\n", " ").strip()
        if summary:
            structure_parts.append(f"内容摘要：{summary}...")
        structure_text = " ".join(structure_parts)

        # style: 风格特征摘要
        style_parts = [f"这是一段{style_type}风格的喜剧创作。"]
        if has_punchline:
            style_parts.append("运用了铺垫与包袱的喜剧技巧。")
        style_text = " ".join(style_parts)

        return {
            "content": content,
            "structure": structure_text,
            "style": style_text,
        }

    @staticmethod
    def _extract_roles(text: str) -> list[str]:
        """从文本中提取角色名（中文+冒号模式）。"""
        roles = set()
        for m in re.finditer(r"([\u4e00-\u9fa5]{1,8})[：:]", text):
            roles.add(m.group(1))
        return sorted(roles)


# ------------------------------------------------------------------ #
# MultiVectorStore —— 多向量表示存储
# ------------------------------------------------------------------ #


class MultiVectorStore:
    """多向量存储。

    基于同一 Embedding 模型，通过不同的 collection + metadata 标记，
    实现"内容向量 / 结构向量 / 风格向量"的多向量表示与检索。

    当前实现（探索阶段）：
    - 使用同一个 Embedding 模型生成向量
    - 通过 ``vector_type`` metadata 区分不同类型
    - 检索时可指定 ``vector_types`` 过滤或跨类型合并

    未来可扩展为：不同类型的文本使用不同的 Embedding 模型，
    真正实现语义空间分离的多向量表示。
    """

    _VECTOR_TYPES = ("content", "structure", "style")

    def __init__(
        self,
        base_collection_name: str = "comedy",
        persist_path: str | None = None,
        embedding_model_name: str | None = None,
    ) -> None:
        """初始化多向量存储。

        Args:
            base_collection_name: 基础集合名称，实际集合名为 ``{base}_{vector_type}``。
            persist_path: 持久化路径。
            embedding_model_name: Embedding 模型标识。
        """
        self.base_name = base_collection_name
        self.stores: dict[str, VectorStore] = {}

        for vt in self._VECTOR_TYPES:
            self.stores[vt] = VectorStore(
                collection_name=f"{base_collection_name}_{vt}",
                persist_path=persist_path,
                embedding_model_name=embedding_model_name,
            )

    # ------------------------------------------------------------------ #
    # 文档入库
    # ------------------------------------------------------------------ #
    def add_documents(
        self,
        documents: list[Document],
        vector_types: list[str] | None = None,
        generate_texts: bool = True,
    ) -> dict[str, list[str]]:
        """将文档添加到指定的向量类型集合中。

        Args:
            documents: 要入库的文档列表。
            vector_types: 要存储的向量类型列表，为 ``None`` 时全部存储。
            generate_texts: 为 ``True`` 时，使用 ``ComedyChunker.generate_vector_texts()``
                为不同向量类型生成不同的语义表示文本。

        Returns:
            dict: {vector_type: [ids]} 映射。
        """
        types = vector_types or list(self._VECTOR_TYPES)
        results: dict[str, list[str]] = {}

        for vt in types:
            if vt not in self.stores:
                raise ValueError(f"未知向量类型 '{vt}'。可用: {self._VECTOR_TYPES}")

            typed_docs: list[Document] = []
            for doc in documents:
                source_id = doc.metadata.get("source_doc_id")
                if not source_id:
                    source_id = str(uuid.uuid4())
                    doc.metadata["source_doc_id"] = source_id

                if generate_texts and vt != "content":
                    texts = ComedyChunker.generate_vector_texts(doc)
                    page_content = texts.get(vt, doc.page_content)
                else:
                    page_content = doc.page_content

                typed_docs.append(
                    Document(
                        page_content=page_content,
                        metadata={
                            **doc.metadata,
                            "vector_type": vt,
                            "source_doc_id": source_id,
                        },
                    )
                )

            ids = self.stores[vt].add_documents(typed_docs)
            results[vt] = ids
            logger.info("向 '%s' 集合入库 %d 条文档", vt, len(ids))

        return results

    # ------------------------------------------------------------------ #
    # 检索
    # ------------------------------------------------------------------ #
    def search(
        self,
        query: str,
        vector_types: list[str] | None = None,
        top_k: int = 5,
        return_original: bool = True,
    ) -> list[Document]:
        """跨类型向量检索，合并去重后返回。

        Args:
            query: 查询文本。
            vector_types: 要检索的向量类型列表，为 ``None`` 时检索全部。
            top_k: 每种类型召回数量。
            return_original: 为 ``True`` 时，按 ``source_doc_id`` 去重并优先返回
                ``content`` 类型的原始文本。

        Returns:
            list[Document]: 合并去重后的文档列表。
        """
        types = vector_types or list(self._VECTOR_TYPES)
        all_results: list[Document] = []

        for vt in types:
            if vt not in self.stores:
                continue
            docs = self.stores[vt].search(query, top_k=top_k)
            for doc in docs:
                doc.metadata["retrieved_from"] = vt
            all_results.extend(docs)

        if return_original:
            return self._deduplicate_and_restore(all_results)
        return self._deduplicate(all_results)

    def search_by_structure(
        self,
        query: str,
        structure_type: str,
        top_k: int = 5,
    ) -> list[Document]:
        """按结构类型过滤检索。

        Args:
            query: 查询文本。
            structure_type: 结构类型过滤，如 ``theory`` / ``script``。
            top_k: 返回数量。

        Returns:
            list[Document]: 过滤后的结果。
        """
        docs = self.stores["content"].search(
            query,
            top_k=top_k,
            filter_dict={"structure_type": structure_type},
        )
        for doc in docs:
            doc.metadata["retrieved_from"] = "content"
        return docs

    def search_by_style(
        self,
        query: str,
        style_type: str,
        top_k: int = 5,
    ) -> list[Document]:
        """按风格类型过滤检索。

        Args:
            query: 查询文本。
            style_type: 风格类型过滤，如 ``satire`` / ``black_humor``。
            top_k: 返回数量。

        Returns:
            list[Document]: 过滤后的结果。
        """
        docs = self.stores["content"].search(
            query,
            top_k=top_k,
            filter_dict={"style_type": style_type},
        )
        for doc in docs:
            doc.metadata["retrieved_from"] = "content"
        return docs

    # ------------------------------------------------------------------ #
    # 管理接口
    # ------------------------------------------------------------------ #
    def count(self, vector_type: str | None = None) -> int:
        """返回指定类型或全部类型的文档总数。"""
        if vector_type:
            store = self.stores.get(vector_type)
            if store is None:
                return 0
            return store.count()
        return sum(s.count() for s in self.stores.values())

    def clear(self, vector_type: str | None = None) -> None:
        """清空指定类型或全部类型的集合。"""
        if vector_type:
            if vector_type in self.stores:
                self.stores[vector_type].clear()
        else:
            for s in self.stores.values():
                s.clear()

    @staticmethod
    def _deduplicate(documents: list[Document]) -> list[Document]:
        """按 page_content 去重，合并多个 vector_type 标记。"""
        seen: dict[str, Document] = {}
        for doc in documents:
            key = doc.page_content
            if key in seen:
                existing = seen[key]
                # 合并 vector_type 列表
                vt_existing = existing.metadata.get("vector_type", [])
                vt_new = doc.metadata.get("vector_type", [])
                if isinstance(vt_existing, str):
                    vt_existing = [vt_existing]
                if isinstance(vt_new, str):
                    vt_new = [vt_new]
                merged = list(dict.fromkeys(vt_existing + vt_new))
                existing.metadata["vector_type"] = merged
                existing.metadata["retrieved_from"] = merged
            else:
                seen[key] = doc
        return list(seen.values())

    @staticmethod
    def _deduplicate_and_restore(documents: list[Document]) -> list[Document]:
        """按 source_doc_id 去重，优先返回 content 类型的原始文本。"""
        by_source: dict[str, dict[str, Any]] = {}

        for doc in documents:
            sid = doc.metadata.get("source_doc_id")
            if not sid:
                # 无 source_doc_id 的文档直接保留
                continue

            if sid not in by_source:
                by_source[sid] = {"doc": doc, "types": set()}

            by_source[sid]["types"].add(doc.metadata.get("vector_type", "unknown"))

            # 优先保留 content 类型的原始文本
            if doc.metadata.get("vector_type") == "content":
                by_source[sid]["doc"] = doc

        result: list[Document] = []
        for sid, info in by_source.items():
            doc = info["doc"]
            types = sorted(info["types"])
            doc.metadata["vector_type"] = types
            doc.metadata["retrieved_from"] = types
            result.append(doc)

        # 把没有 source_doc_id 的文档也加回来
        no_sid = [d for d in documents if not d.metadata.get("source_doc_id")]
        return result + no_sid
