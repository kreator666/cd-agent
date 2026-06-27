"""理论知识入库脚本。

用法示例：
    python scripts/ingest_theory.py \
        --input data/knowledge/knowledge_items.jsonl \
        --embedding-model hf-local
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 把项目根目录加入 sys.path，确保能导入 src 包
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from comedy_agent.core.knowledge_models import KnowledgeItem  # noqa: E402
from comedy_agent.rag.theory_store import TheoryStore  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

DEFAULT_INPUT_PATH = PROJECT_ROOT / "data" / "knowledge" / "knowledge_items.jsonl"


def load_items(path: Path) -> list[KnowledgeItem]:
    """从 JSONL 加载 KnowledgeItem 列表。"""
    items: list[KnowledgeItem] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            items.append(KnowledgeItem(**data))
    logger.info("从 %s 加载 %d 条知识条目", path, len(items))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="把结构化理论知识入库到向量库")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="输入 JSONL 路径",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=None,
        help="Embedding 模型名（默认使用 settings.default_embedding_model）",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="入库前清空已有集合",
    )
    args = parser.parse_args()

    if not args.input.exists():
        logger.error("输入文件不存在: %s", args.input)
        sys.exit(1)

    items = load_items(args.input)
    if not items:
        logger.error("没有要入库的知识条目")
        sys.exit(1)

    store = TheoryStore(embedding_model_name=args.embedding_model)
    if args.clear:
        store.clear()
        logger.info("已清空集合 %s", store.vector_store.collection_name)

    ids = store.ingest(items)
    logger.info(
        "成功入库 %d 条知识条目到集合 '%s'，当前共 %d 条",
        len(ids),
        store.vector_store.collection_name,
        store.count(),
    )

    # 简单验证：检索一条核心概念
    results = store.search("三番四抖", top_k=1)
    if results:
        logger.info("验证检索成功: %s", results[0].title)
    else:
        logger.warning("验证检索未返回结果")


if __name__ == "__main__":
    main()
