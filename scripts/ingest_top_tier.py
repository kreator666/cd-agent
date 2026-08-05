#!/usr/bin/env python3
"""顶流脱口秀文稿入库 CLI。

用法示例：
    # 按空行/默认切分
    python scripts/ingest_top_tier.py \
        --input data/top_tier/ \
        --collection top_tier_scripts \
        --kind standup \
        --style 自嘲

    # 按正则切分（如按【选手：xxx】分段）
    python scripts/ingest_top_tier.py \
        --input data/need-data/tf/2.md \
        --collection top_tier_scripts \
        --split-by "(?=【选手：)" \
        --model ollama-qwen2.5
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comedy_agent.core.annotation import annotate_text, build_embedding_text, load_raw_segments, process_texts
from comedy_agent.core.example_retriever import ingest_annotations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

DEFAULT_COLLECTION = "top_tier_scripts"


def _split_by_regex(text: str, pattern: str) -> list[tuple[str, str]]:
    """按正则切分文本，并尝试从每段提取标题作为 source 后缀。"""
    parts = re.split(pattern, text)
    results: list[tuple[str, str]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 尝试提取段内标题，如 【选手：贾耗】
        title = ""
        title_match = re.match(r"【选手：([^】]+)】", part)
        if title_match:
            title = title_match.group(1).strip()
        results.append((title, part))
    return results


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
    parser.add_argument(
        "--split-by",
        dest="split_by",
        default=None,
        help="按正则切分文本，例如 '(?=【选手：)'",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"输入路径不存在: {input_path}", file=sys.stderr)
        return 1

    if args.split_by and input_path.is_file():
        text = input_path.read_text(encoding="utf-8")
        segments = _split_by_regex(text, args.split_by)
    else:
        segments = load_raw_segments(input_path)

    if not segments:
        print("未找到可标注的文本段落", file=sys.stderr)
        return 1

    print(f"共加载 {len(segments)} 段候选文本")

    examples = []
    for title, seg in segments:
        source = str(input_path)
        if title:
            source = f"{source} | {title}"
        ex = annotate_text(
            seg,
            model=args.model,
            kind=args.kind,
            style=args.style,
            source=source,
        )
        ex.embedding_text = build_embedding_text(ex)
        examples.append(ex)

    ids = ingest_annotations(examples, collection_name=args.collection)
    print(f"成功写入 {len(ids)} 条顶流文稿到集合 '{args.collection}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
