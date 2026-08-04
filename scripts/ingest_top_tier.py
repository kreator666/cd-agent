#!/usr/bin/env python3
"""顶流脱口秀文稿入库 CLI。

用法示例：
    python scripts/ingest_top_tier.py \
        --input data/top_tier/ \
        --collection top_tier_scripts \
        --kind standup \
        --style 自嘲

也可以指定单个文件：
    python scripts/ingest_top_tier.py \
        --input data/top_tier/专场A.txt \
        --collection top_tier_scripts
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comedy_agent.core.annotation import load_raw_segments, process_texts
from comedy_agent.core.example_retriever import ingest_annotations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

DEFAULT_COLLECTION = "top_tier_scripts"


def main() -> int:
    parser = argparse.ArgumentParser(description="顶流脱口秀文稿向量化入库")
    parser.add_argument("--input", required=True, help="输入文件或目录路径")
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help=f"目标向量库集合名称（默认 {DEFAULT_COLLECTION}）",
    )
    parser.add_argument("--kind", default="standup", help="喜剧种类（默认 standup）")
    parser.add_argument("--style", default=None, help="默认风格")
    parser.add_argument("--model", default=None, help="标注模型名称")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"输入路径不存在: {input_path}", file=sys.stderr)
        return 1

    segments = load_raw_segments(input_path)
    if not segments:
        print("未找到可标注的文本段落", file=sys.stderr)
        return 1

    print(f"共加载 {len(segments)} 段候选文本")
    examples = process_texts(
        [seg for _, seg in segments],
        model=args.model,
        kind=args.kind,
        style=args.style,
        source=str(input_path),
    )

    ids = ingest_annotations(examples, collection_name=args.collection)
    print(f"成功写入 {len(ids)} 条顶流文稿到集合 '{args.collection}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
