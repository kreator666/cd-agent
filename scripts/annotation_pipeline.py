#!/usr/bin/env python3
"""段子标注流水线 CLI。

用法示例：
    python scripts/annotation_pipeline.py \
        --input data/raw_jokes.txt \
        --output data/annotations.jsonl \
        --kind standup \
        --style 自嘲

也可以处理整个目录：
    python scripts/annotation_pipeline.py \
        --input data/raw_jokes/ \
        --output data/annotations.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 把项目 src 加入路径，确保能导入 comedy_agent
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comedy_agent.core.annotation import (
    AnnotatedExample,
    generate_schema_json,
    load_raw_segments,
    process_texts,
    save_annotations,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="脱口秀文本标注流水线")
    parser.add_argument("--input", default=None, help="输入文件或目录路径")
    parser.add_argument("--output", default=None, help="输出 JSONL 路径")
    parser.add_argument("--kind", default="standup", help="喜剧种类（默认 standup）")
    parser.add_argument("--style", default=None, help="默认风格")
    parser.add_argument("--model", default=None, help="标注模型名称")
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="标注完成后直接写入向量库",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="写入向量库的目标集合名称（默认 comedy_knowledge）",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="仅生成 data/annotation_schema.json 并退出",
    )
    args = parser.parse_args()

    if args.schema:
        schema_path = Path("data/annotation_schema.json")
        schema_path.write_text(
            json.dumps(generate_schema_json(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Schema 已保存到 {schema_path}")
        return 0

    if args.ingest and not args.input:
        print("--ingest 模式需要 --input", file=sys.stderr)
        return 1

    if not args.input or not args.output:
        print("--input 和 --output 为必填项", file=sys.stderr)
        return 1

    segments = load_raw_segments(Path(args.input))
    if not segments:
        print("未找到可标注的文本段落", file=sys.stderr)
        return 1

    print(f"共加载 {len(segments)} 段候选文本")
    examples = process_texts(
        [seg for _, seg in segments],
        model=args.model,
        kind=args.kind,
        style=args.style,
        source=str(args.input),
    )
    save_annotations(examples, Path(args.output))
    print(f"标注完成，输出 {len(examples)} 条示例到 {args.output}")

    if args.ingest:
        from comedy_agent.core.example_retriever import ingest_annotations

        ids = ingest_annotations(examples, collection_name=args.collection)
        print(f"已写入 {len(ids)} 条到向量库集合 '{args.collection or 'comedy_knowledge'}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
