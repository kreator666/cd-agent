"""喜剧理论知识工具函数。

提供一组高层接口，供 Planner / Writer 或未来 Tool 调用：
- query_theory：查询概念/技法定义
- list_techniques：列主题相关技法
- get_pattern：获取结构模板
- check_rule：检查文本是否可能违反创作规则

当前实现基于 `retrieve_knowledge`；后续可快速注册为 LangChain Tool。
"""

from __future__ import annotations

from comedy_agent.core.knowledge_models import KnowledgeItem
from comedy_agent.core.knowledge_system import _tokenize, retrieve_knowledge


def _format_items(items: list[KnowledgeItem]) -> str:
    """把 KnowledgeItem 列表格式化为可读文本。"""
    if not items:
        return "未找到相关知识。"

    parts: list[str] = []
    for idx, item in enumerate(items, 1):
        body = item.summary or item.content
        source = f"来源：{item.source}" if item.source else ""
        parts.append(
            f"{idx}. {item.title}（{item.category}）\n{body}\n{source}".strip()
        )
    return "\n\n".join(parts)


def query_theory(term: str, top_k: int = 3) -> str:
    """查询某个喜剧理论概念或技法的定义。

    Args:
        term: 术语，如"三番四抖"、"预期违背"。
        top_k: 返回结果数量。

    Returns:
        格式化的理论知识文本。
    """
    items = retrieve_knowledge(term, top_k=top_k)
    if not items:
        return f"未找到与「{term}」相关的理论知识。"
    return f"关于「{term}」的理论知识：\n\n{_format_items(items)}"


def list_techniques(topic: str, top_k: int = 5) -> str:
    """列出与某个主题相关的喜剧技法。

    Args:
        topic: 主题，如"加班"、"人工智能"、"情感"。
        top_k: 返回结果数量。

    Returns:
        技法列表文本。
    """
    items = retrieve_knowledge(topic, category="technique", top_k=top_k)
    if not items:
        return f"未找到与「{topic}」相关的喜剧技法。"

    lines = [f"- {item.title}：{item.summary or item.content[:80]}" for item in items]
    return f"与「{topic}」相关的喜剧技法：\n" + "\n".join(lines)


def get_pattern(name: str, top_k: int = 3) -> str:
    """获取某个结构模板的详细说明。

    Args:
        name: 模板名，如"小品三幕结构"。
        top_k: 返回结果数量。

    Returns:
        结构模板说明文本。
    """
    items = retrieve_knowledge(name, category="pattern", top_k=top_k)
    if not items:
        return f"未找到名为「{name}」的结构模板。"
    return f"结构模板「{name}」：\n\n{_format_items(items)}"


def check_rule(text: str, rule_type: str | None = None, top_k: int = 3) -> str:
    """检查文本是否可能违反某项喜剧创作规则。

    当前为轻量级关键词匹配；后续可升级为 LLM 评估。

    Args:
        text: 待检查的文本。
        rule_type: 可选，指定规则类型关键词，如"笑点"、"铺垫"。
        top_k: 召回规则数量。

    Returns:
        规则检查结论文本。
    """
    query = rule_type or text
    items = retrieve_knowledge(query, category="rule", top_k=top_k)
    if not items:
        return "未找到相关创作规则。"

    text_tokens = _tokenize(text)
    flags: list[str] = []
    for item in items:
        rule_text = " ".join(
            [item.title, item.summary, item.content] + item.related_terms
        )
        rule_tokens = _tokenize(rule_text)
        overlap = text_tokens & rule_tokens
        if overlap:
            flags.append(
                f"可能违反「{item.title}」：文本中出现了 {'、'.join(sorted(overlap))}。"
            )

    if flags:
        return "规则检查：\n" + "\n".join(flags)
    return "未检测到明显违规。"
