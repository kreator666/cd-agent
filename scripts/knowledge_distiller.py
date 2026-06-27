"""知识蒸馏器 CLI 入口。

用法示例：
    python scripts/knowledge_distiller.py \
        --input data/knowledge/theory_corpus.md \
        --output data/knowledge/knowledge_items.jsonl
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 把项目根目录加入 sys.path，确保能导入 src 包
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from comedy_agent.core.knowledge_distiller import (  # noqa: E402
    DEFAULT_CORPUS_PATH,
    DEFAULT_OUTPUT_PATH,
    distill,
    parse_corpus,
    save_items,
)
from comedy_agent.models.factory import ModelFactory  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="从喜剧理论语料中蒸馏结构化知识")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_CORPUS_PATH,
        help="理论语料 Markdown 路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="输出 JSONL 路径",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="指定 LLM 模型名（默认按 analytical 任务类型解析）",
    )
    args = parser.parse_args()

    sections = parse_corpus(args.input)
    if not sections:
        logger.error("未从 %s 解析出任何理论段落", args.input)
        sys.exit(1)

    llm = ModelFactory.get_model(name=args.model, task_type="analytical")
    items = distill(sections, llm=llm)
    save_items(items, args.output)


if __name__ == "__main__":
    main()
