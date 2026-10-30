"""302.AI API 列表解析工具。

从 https://doc.302.ai/llms.txt 拉取最新 API 列表，支持按关键字和分类搜索。
"""

from __future__ import annotations

import argparse
import re
import sys
from urllib.request import urlopen

LLMS_TXT_URL = "https://doc.302.ai/llms.txt"


def fetch_llms_txt() -> str:
    """拉取 302.AI 的 llms.txt 内容。"""
    with urlopen(LLMS_TXT_URL, timeout=30) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


def parse_llms_txt(content: str) -> list[dict[str, str]]:
    """解析 llms.txt，返回 API 条目列表。

    每行格式示例：
    - 语言大模型 > 列出模型 [Models（列出模型）](https://doc.302.ai/147522038e0.md): 描述
    """
    apis: list[dict[str, str]] = []
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        # 去掉开头的 -
        line = line[1:].strip()
        # 提取 markdown 链接 [name](url)
        link_match = re.search(r"\[(([^\]]+))\]\(([^)]+)\)", line)
        if not link_match:
            continue
        name = link_match.group(1)
        link = link_match.group(3)
        # 链接前的内容是分类路径
        prefix = line[: link_match.start()].strip()
        # 链接后的冒号后是描述
        suffix = line[link_match.end() :].strip()
        description = suffix.lstrip(":").strip()
        # 分类路径按 > 拆分
        category = " > ".join(part.strip() for part in prefix.split(">") if part.strip())
        apis.append(
            {
                "name": name,
                "category": category,
                "description": description,
                "link": link,
            }
        )
    return apis


def search_apis(
    apis: list[dict[str, str]],
    keyword: str | None = None,
    category: str | None = None,
) -> list[dict[str, str]]:
    """按关键字和/或分类过滤 API 列表。"""
    results = apis
    if category:
        cat_lower = category.lower()
        results = [a for a in results if cat_lower in a["category"].lower()]
    if keyword:
        kw_lower = keyword.lower()
        results = [
            a
            for a in results
            if kw_lower in a["name"].lower()
            or kw_lower in a["description"].lower()
            or kw_lower in a["category"].lower()
        ]
    return results


def extract_doc_id(link: str) -> str:
    """从 doc.302.ai 链接中提取文档 ID。"""
    match = re.search(r"doc\.302\.ai/([a-zA-Z0-9]+)\.md", link)
    return match.group(1) if match else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="搜索 302.AI API 列表")
    parser.add_argument("keyword", nargs="?", help="搜索关键字")
    parser.add_argument("category", nargs="?", help="分类过滤")
    parser.add_argument("--limit", type=int, default=20, help="最多显示条数")
    args = parser.parse_args()

    content = fetch_llms_txt()
    apis = parse_llms_txt(content)
    results = search_apis(apis, keyword=args.keyword, category=args.category)

    if not results:
        print("未找到匹配的 API")
        return

    for i, api in enumerate(results[: args.limit], 1):
        print(f"{i}. {api['name']}")
        print(f"   Category: {api['category']}")
        print(f"   Description: {api['description']}")
        print(f"   Docs: {api['link']}")
        print()


if __name__ == "__main__":
    main()
