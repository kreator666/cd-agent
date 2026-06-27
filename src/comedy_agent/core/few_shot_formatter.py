"""Few-shot 格式化器。

将检索到的示例（AnnotatedExample / Document）格式化为 Prompt 可用的文本块。
"""

from __future__ import annotations

from langchain_core.documents import Document

from comedy_agent.core.annotation import AnnotatedExample


def format_examples(
    examples: list[AnnotatedExample] | list[Document],
    include_setup: bool = True,
    include_punchline: bool = True,
    include_tags: bool = False,
    max_tokens: int | None = None,
) -> str:
    """将示例列表格式化为 Prompt 文本。

    Args:
        examples: 示例列表，可以是 AnnotatedExample 或 Document。
        include_setup: 是否展示铺垫。
        include_punchline: 是否展示笑点。
        include_tags: 是否展示标签。
        max_tokens: 可选的 Token 预算（按中文字符 1.5 tokens/字 估算），超出时截断。

    Returns:
        格式化后的示例文本；无示例时返回空字符串。
    """
    if not examples:
        return ""

    lines = ["【参考示例】"]
    total_chars = 0
    budget_chars = int((max_tokens or 0) / 1.5) if max_tokens else None

    for idx, ex in enumerate(examples, 1):
        if isinstance(ex, Document):
            item = AnnotatedExample(
                content=ex.page_content,
                topic=ex.metadata.get("topic", ""),
                style=ex.metadata.get("style", ""),
                setup=ex.metadata.get("setup", ""),
                punchline=ex.metadata.get("punchline", ""),
                tags=ex.metadata.get("tags", []),
            )
        else:
            item = ex

        block_parts = [f"示例 {idx}:"]
        header_parts = []
        if item.topic:
            header_parts.append(f"话题：{item.topic}")
        if item.style:
            header_parts.append(f"风格：{item.style}")
        if include_tags and item.tags:
            header_parts.append(f"标签：{'/'.join(item.tags)}")
        if header_parts:
            block_parts.append(" | ".join(header_parts))

        if include_setup and item.setup:
            block_parts.append(f"铺垫：{item.setup}")
        if include_punchline and item.punchline:
            block_parts.append(f"笑点：{item.punchline}")
        # 兜底：如果没有 setup/punchline，展示完整文本
        if not (item.setup or item.punchline):
            block_parts.append(f"文本：{item.content}")

        block = "\n".join(block_parts)

        if budget_chars is not None:
            total_chars += len(block)
            if total_chars > budget_chars and idx > 1:
                break

        lines.append(block)
        lines.append("")

    return "\n".join(lines).strip()
