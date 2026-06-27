"""知识蒸馏器核心逻辑。

从喜剧理论语料 Markdown 中解析段落，并调用 LLM 提取结构化的 KnowledgeItem。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from comedy_agent.core.knowledge_models import (
    DistillationOutput,
    KnowledgeItem,
)
from comedy_agent.models.factory import ModelFactory

logger = logging.getLogger(__name__)


DEFAULT_CORPUS_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "theory_corpus.md"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "knowledge_items.jsonl"


@dataclass
class RawTheorySection:
    """从 Markdown 语料中解析出的原始理论段落。"""

    title: str
    category: str
    source: str
    content: str


SYSTEM_PROMPT = """你是一位喜剧理论知识蒸馏专家。

任务：根据下面给出的喜剧理论段落，提取结构化的知识条目。

输出要求：
1. 每个段落在输出中对应一条 KnowledgeItem，不要遗漏也不要重复。
2. 必须保留原始段落的 title、category、source（source 字段原样复制，不可留空）。
3. id 使用短横线连接的小写英文（如 "three-setup-four-punch"），保持唯一。
4. summary 用 1 句话概括该知识点的核心含义。
5. content 保留原文关键信息，可适当精简但不得改变原意。
6. entity_triples 必须提取至少 2 个与喜剧创作相关的 (实体, 关系, 实体) 三元组，例如：
   - {"subject": "三番四抖", "relation": "属于", "object": "结构技巧"}
   - {"subject": "铺垫", "relation": "用于", "object": "建立预期"}
7. related_terms 列出相关术语或别名，不少于 3 个。
8. embedding_text 留空即可，系统会自动生成。

只能返回结构化结果，不要输出额外解释。"""


def parse_corpus(corpus_path: Path) -> list[RawTheorySection]:
    """解析理论语料 Markdown，按二级标题拆分段落。"""
    text = corpus_path.read_text(encoding="utf-8")
    parts = re.split(r"\n## ", text)
    sections: list[RawTheorySection] = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        title = lines[0].strip().lstrip("#").strip()
        if not title or title.startswith("喜剧创作核心理论"):
            continue

        category = ""
        source = ""
        content_lines: list[str] = []
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("类别:") or stripped.startswith("类别："):
                category = stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
            elif stripped.startswith("来源:") or stripped.startswith("来源："):
                source = stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
            else:
                content_lines.append(line)

        content = "\n".join(content_lines).strip()
        if not title or not category or not content:
            logger.warning("段落解析不完整，跳过: title=%s category=%s", title, category)
            continue

        sections.append(
            RawTheorySection(
                title=title,
                category=category,
                source=source,
                content=content,
            )
        )

    logger.info("从 %s 解析出 %d 个理论段落", corpus_path, len(sections))
    return sections


def _build_user_input(sections: list[RawTheorySection]) -> str:
    """把原始段落组织成给 LLM 的输入文本。"""
    blocks: list[dict[str, Any]] = []
    for sec in sections:
        blocks.append(
            {
                "title": sec.title,
                "category": sec.category,
                "source": sec.source,
                "content": sec.content,
            }
        )
    return json.dumps(blocks, ensure_ascii=False, indent=2)


def distill(
    sections: list[RawTheorySection],
    llm: BaseChatModel | None = None,
) -> list[KnowledgeItem]:
    """调用 LLM 把原始段落蒸馏为结构化知识条目。"""
    if not sections:
        return []

    if llm is None:
        llm = ModelFactory.get_model(task_type="analytical")

    user_input = _build_user_input(sections)
    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", f"请提取以下 {len(sections)} 个理论知识段落：\n\n{user_input}"),
    ]

    try:
        structured_llm = llm.with_structured_output(DistillationOutput)
        result = structured_llm.invoke(messages)
        items = result.items
    except Exception as e:
        logger.warning("结构化蒸馏失败，尝试文本回退: %s", e)
        items = _fallback_distill(llm, messages)

    valid_categories = {"concept", "technique", "pattern", "rule"}
    title_to_source = {sec.title: sec.source for sec in sections}
    seen_ids: set[str] = set()
    processed: list[KnowledgeItem] = []
    for item in items:
        if item.category not in valid_categories:
            logger.warning("条目 %s 的类别 %s 不合法，跳过", item.title, item.category)
            continue
        # source 回退：LLM 可能漏填，按标题匹配原始段落的 source
        if not item.source and item.title in title_to_source:
            item.source = title_to_source[item.title]
        # ID 去重
        original_id = item.id
        counter = 1
        while item.id in seen_ids:
            counter += 1
            item.id = f"{original_id}-{counter}"
        seen_ids.add(item.id)
        # 如果 LLM 没给出三元组，补充一个默认三元组保证下游可用
        if not item.entity_triples:
            item.entity_triples.append(
                {
                    "subject": item.title,
                    "relation": "属于",
                    "object": _category_cn(item.category),
                }
            )
        if not item.embedding_text:
            item.embedding_text = item.build_embedding_text()
        processed.append(item)

    logger.info("蒸馏完成，共 %d 条有效知识条目", len(processed))
    return processed


def _category_cn(category: str) -> str:
    """把类别英文映射为中文，用于默认三元组。"""
    mapping = {
        "concept": "概念",
        "technique": "技法",
        "pattern": "结构模板",
        "rule": "规则",
    }
    return mapping.get(category, category)


def _fallback_distill(
    llm: BaseChatModel,
    messages: list,
) -> list[KnowledgeItem]:
    """结构化输出失败时，尝试让 LLM 返回 JSON 字符串并手动解析。"""
    fallback_messages = messages + [
        (
            "human",
            "请直接输出一个合法的 JSON 对象，字段为 {\"items\": [...]}，不要带 markdown 代码块。",
        )
    ]
    try:
        response = llm.invoke(fallback_messages)
        content = str(getattr(response, "content", response))
        content = re.sub(r"```(?:json)?\s*", "", content).replace("```", "").strip()
        data = json.loads(content)
        items = [KnowledgeItem(**raw) for raw in data.get("items", [])]
        return items
    except Exception as e2:
        logger.error("回退蒸馏也失败: %s", e2)
        return []


def save_items(items: list[KnowledgeItem], output_path: Path) -> None:
    """把知识条目保存为 JSONL。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(item.model_dump_json(ensure_ascii=False) + "\n")
    logger.info("已保存 %d 条知识条目到 %s", len(items), output_path)
