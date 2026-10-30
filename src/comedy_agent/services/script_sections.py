"""分段打磨 —— 评测结果正文的段落解析与合并。

``EvalResult.content`` 是纯文本整段稿，正文中内嵌中文段落标签，形如::

    【脱口秀标题】
    xxx
    【开场 Hook】
    xxx

本模块提供纯函数，不依赖数据库，供 API 层解析为可单段润色/重新生成
的结构，并能无损合并回全文。
"""

from __future__ import annotations

import re

_LABEL_RE = re.compile(r"^\s*【(.+?)】\s*$")
_FALLBACK_SPLIT_RE = re.compile(r"\n\s*\n")
_PREAMBLE_TITLE = "标题"


def _strip_blank_lines(lines: list[str]) -> list[str]:
    """去掉行列表首尾的空行（保留内部空行与换行）。"""
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def parse_sections(content: str) -> list[dict]:
    """把评测结果正文解析为段落列表。

    行首匹配 ``^【(.+?)】\\s*$``（允许首尾空白）的行作为段标题，
    开启新段；第一个标签之前的非空内容归入 title 固定为 ``"标题"``
    的段。完全没有标签时，按空行切分兜底，标题自动生成 ``"第N段"``。

    Returns:
        [{"index": int, "title": str, "text": str, "has_label": bool}, ...]
        ``has_label`` 为 True 表示该段有原始标签，合并时输出 ``【title】``。
    """
    if not content or not content.strip():
        return []

    lines = content.splitlines()
    label_lines = [i for i, line in enumerate(lines) if _LABEL_RE.match(line)]

    if label_lines:
        sections: list[dict] = []

        # 第一个标签之前的非空内容作为 "标题" 段
        preamble = _strip_blank_lines(lines[: label_lines[0]])
        if preamble:
            sections.append(
                {
                    "index": len(sections),
                    "title": _PREAMBLE_TITLE,
                    "text": "\n".join(preamble),
                    "has_label": False,
                }
            )

        for pos, line_idx in enumerate(label_lines):
            end = label_lines[pos + 1] if pos + 1 < len(label_lines) else len(lines)
            title = _LABEL_RE.match(lines[line_idx]).group(1).strip()  # type: ignore[union-attr]
            body_lines = _strip_blank_lines(lines[line_idx + 1 : end])
            sections.append(
                {
                    "index": len(sections),
                    "title": title,
                    "text": "\n".join(body_lines),
                    "has_label": True,
                }
            )
        return sections

    # 兜底：按空行切分
    chunks = [c for c in _FALLBACK_SPLIT_RE.split(content.strip()) if c.strip()]
    return [
        {
            "index": i,
            "title": f"第{i + 1}段",
            "text": chunk.strip("\n"),
            "has_label": False,
        }
        for i, chunk in enumerate(chunks)
    ]


def merge_sections(sections: list[dict]) -> str:
    """把段落列表合并回全文。

    有原始标签的段输出 ``【title】\\n text``；
    兜底段（自动生成标题的）只输出 text 不带标签。
    """
    parts: list[str] = []
    for section in sections:
        text = section.get("text", "")
        if section.get("has_label"):
            parts.append(f"【{section['title']}】\n{text}")
        else:
            parts.append(text)
    return "\n\n".join(parts)
