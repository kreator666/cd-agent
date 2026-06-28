#!/usr/bin/env python3
"""将标注示例写入向量库，供 Writer 动态检索使用。

用法示例：
    python scripts/ingest_annotations.py --input examples/annotation_examples.jsonl

也可以指定用户个人库：
    python scripts/ingest_annotations.py \
        --input examples/annotation_examples.jsonl \
        --user-id user_123 \
        --collection user_knowledge_user_123
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comedy_agent.core.annotation import AnnotatedExample
from comedy_agent.core.example_retriever import ingest_annotations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


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
                logging.warning("跳过无效 JSONL 行: %s", e)

    return [AnnotatedExample(**record) for record in records]


def main() -> int:
    parser = argparse.ArgumentParser(description="将标注示例写入向量库")
    parser.add_argument("--input", required=True, help="标注 JSON/JSONL 文件路径")
    parser.add_argument("--user-id", default=None, help="用户 ID（写入个人库）")
    parser.add_argument("--collection", default=None, help="自定义集合名称")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"文件不存在: {input_path}", file=sys.stderr)
        return 1

    annotations = _load_annotations(input_path)
    if not annotations:
        print("未加载到任何标注示例", file=sys.stderr)
        return 1

    print(f"加载了 {len(annotations)} 条标注示例")
    ids = ingest_annotations(
        annotations,
        user_id=args.user_id,
        collection_name=args.collection,
    )
    print(f"成功写入 {len(ids)} 条到向量库")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
