#!/usr/bin/env python3
"""将默认标注示例写入 comedy_knowledge 集合。

用法：
    python scripts/seed_default_examples.py

该脚本会读取 examples/annotation_examples.jsonl，按 example_id 去重后写入
默认 Few-shot 示例集合 ``comedy_knowledge``。可重复执行，不会重复入库。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comedy_agent.core.annotation import AnnotatedExample, build_embedding_text
from comedy_agent.core.config import settings
from comedy_agent.rag.vector_store import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_INPUT = Path(__file__).resolve().parents[1] / "examples" / "annotation_examples.jsonl"
DEFAULT_COLLECTION = "comedy_knowledge"


def _load_annotations(path: Path) -> list[AnnotatedExample]:
    """从 JSON/JSONL 加载标注示例。"""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    records: list[dict] = []
    if text.startswith("["):
        try:
            records = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 数组解析失败: {e}")
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning("跳过无效 JSONL 行: %s", e)

    return [AnnotatedExample(**record) for record in records]


def _example_to_document(example: AnnotatedExample):
    """把 AnnotatedExample 转成 LangChain Document。"""
    from langchain_core.documents import Document

    meta = example.model_dump()
    meta.pop("embedding_text", None)
    meta.pop("content", None)
    meta["content"] = example.content
    return Document(page_content=example.embedding_text, metadata=meta)


def main() -> int:
    parser = argparse.ArgumentParser(description="默认标注示例入库")
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="标注 JSON/JSONL 文件路径",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="目标集合名",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="Embedding 模型标识，默认使用 settings.default_embedding_model",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"文件不存在: {input_path}", file=sys.stderr)
        return 1

    annotations = _load_annotations(input_path)
    if not annotations:
        print("未加载到任何标注示例", file=sys.stderr)
        return 1

    # 补全 embedding_text
    for ex in annotations:
        if not ex.embedding_text:
            ex.embedding_text = build_embedding_text(ex)

    # 初始化向量存储
    embedding_model = args.embedding_model or settings.default_embedding_model
    logger.info(
        "正在初始化集合 '%s'，使用 Embedding 模型 '%s'...",
        args.collection,
        embedding_model,
    )
    store = VectorStore(
        collection_name=args.collection,
        embedding_model_name=embedding_model,
    )

    # 按 example_id 去重
    candidate_ids = [ex.example_id for ex in annotations]
    try:
        existing = store.collection.get(ids=candidate_ids, include=[])
        existing_ids = set(existing.get("ids", []))
    except Exception as e:
        logger.warning("查询已有文档失败，假设全部为新文档: %s", e)
        existing_ids = set()

    new_examples = [ex for ex in annotations if ex.example_id not in existing_ids]
    if not new_examples:
        print(f"全部 {len(annotations)} 条示例已存在于集合 '{args.collection}'，无需写入")
        return 0

    documents = [_example_to_document(ex) for ex in new_examples]
    ids = [ex.example_id for ex in new_examples]

    try:
        added = store.add_documents(documents, ids=ids)
    except Exception as e:
        logger.error("写入向量库失败: %s", e, exc_info=True)
        print(f"写入失败: {e}", file=sys.stderr)
        return 1

    print(
        f"集合 '{args.collection}' 已有 {len(existing_ids)} 条，"
        f"本次新增 {len(added)} 条，共计 {store.count()} 条"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
