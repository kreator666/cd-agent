"""提示词段落解析与组合工具。

把 SKILL.md 中的系统提示词拆分为可组合的章节段落，
供测试程序与后端 /eval API 共用，保证生产与测试的解析行为一致。
"""

from __future__ import annotations

import re
from itertools import chain, combinations
from pathlib import Path
from typing import Iterable


# --------------------------------------------------------------------------- #
# 默认用户输入与参数解析
# --------------------------------------------------------------------------- #


def parse_user_params(user_input: str) -> dict[str, str]:
    """从用户输入文本中解析四维度参数，用于填充提示词模板。"""
    params: dict[str, str] = {}
    patterns = {
        "topic": r"话题[：:]\s*([^态度偏见情绪时长\n]+)",
        "attitude": r"态度[：:]\s*([^偏见情绪时长\n]+)",
        "bias": r"偏见[：:]\s*([^情绪时长\n]+)",
        "emotion": r"情绪[：:]\s*([^时长\n]+)",
        "duration": r"时长[：:]\s*(\d+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, user_input)
        if match:
            params[key] = match.group(1).strip()
    return params


def build_user_input(
    user_input: str,
    prompt_template: str = "",
    default_duration: int = 3,
    extra_defaults: dict[str, str] | None = None,
) -> str:
    """根据提示词模板格式化用户输入；解析失败时回退到原始输入。"""
    if not prompt_template:
        return user_input

    params = parse_user_params(user_input)
    if not params:
        return user_input

    params.setdefault("duration", str(default_duration))
    if extra_defaults:
        for key, value in extra_defaults.items():
            params.setdefault(key, value)

    try:
        return prompt_template.format(**params)
    except (KeyError, ValueError):
        return user_input


# --------------------------------------------------------------------------- #
# SKILL.md 解析
# --------------------------------------------------------------------------- #


def extract_system_prompt_block(markdown_text: str) -> str:
    """从 SKILL.md 文本中提取 ``## 系统提示词`` 区块内容。

    区块范围从 ``## 系统提示词`` 开始，到 ``## 提示词模板`` 或文件结束为止。
    会自动去除代码块标记（```markdown / ```）。
    """
    sys_start = markdown_text.find("## 系统提示词")
    if sys_start == -1:
        return ""

    sys_end = markdown_text.find("## 提示词模板", sys_start)
    if sys_end == -1:
        system_block = markdown_text[sys_start:]
    else:
        system_block = markdown_text[sys_start:sys_end]

    # 去掉代码块标记
    system_block = re.sub(r"^```markdown\n?", "", system_block, flags=re.MULTILINE)
    system_block = re.sub(r"\n```\s*$", "", system_block, flags=re.MULTILINE)
    # 去掉二级标题本身
    system_block = re.sub(r"^## 系统提示词\n+", "", system_block, flags=re.MULTILINE)
    return system_block.strip()


def parse_prompt_template(markdown_text: str) -> str:
    """从 SKILL.md 中提取 ``## 提示词模板`` 内容。

    与 ``src/comedy_agent/skills/loader.py`` 中的解析逻辑保持一致：
    优先匹配代码块格式，其次匹配纯文本格式。
    """
    pt_match = re.search(
        r"^##\s+提示词模板\s*\n+```.*?\n(.*?)```",
        markdown_text,
        re.MULTILINE | re.DOTALL,
    )
    if pt_match:
        return pt_match.group(1).strip()

    pt_match = re.search(
        r"^##\s+提示词模板\s*\n+(.+?)(?=\n^##|\Z)",
        markdown_text,
        re.MULTILINE | re.DOTALL,
    )
    if pt_match:
        return pt_match.group(1).strip()

    return ""


def parse_sections(
    markdown_text: str,
) -> tuple[str, list[tuple[str, str]], str]:
    """把系统提示词拆分为：固定开头、可选中间段落、固定结尾。

    拆分规则：
    - 按 Markdown 一级标题 ``# `` 切分。
    - 第一个一级标题之前的内容（通常是角色定义）作为固定开头 intro。
    - 标题中包含 ``最终原则`` 或 ``最终输出约束`` 的段落作为固定结尾 outro。
    - 其余一级标题段落作为可自由组合的中间段落。

    Returns:
        (intro, [(title, body), ...], outro)
    """
    # 先把 "【最终输出约束..." 这种独立块单独切出来，不作为标题段落
    constraint_pattern = re.compile(r"(【最终输出约束.*)$", re.DOTALL)
    constraint_match = constraint_pattern.search(markdown_text)
    trailing_constraint = ""
    if constraint_match:
        markdown_text = markdown_text[: constraint_match.start()].rstrip()
        trailing_constraint = constraint_match.group(1).strip()

    # 按一级标题切分，保留标题行
    parts = re.split(r"\n(?=# )", markdown_text)

    intro = parts[0].strip() if parts else ""
    middle: list[tuple[str, str]] = []
    final_principle_text = ""

    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

        # 最终原则 / 最终输出约束 作为固定结尾
        if "最终原则" in title or "最终输出约束" in title:
            final_principle_text = f"{title}\n\n{body}" if body else title
            continue

        middle.append((title, body))

    outro_parts: list[str] = []
    if final_principle_text:
        outro_parts.append(final_principle_text)
    if trailing_constraint:
        outro_parts.append(trailing_constraint)

    outro = (
        "\n\n--------------------------------------------------\n\n".join(outro_parts)
        if outro_parts
        else ""
    )
    return intro, middle, outro


def parse_plus_sections(markdown_text: str) -> list[tuple[str, str]]:
    """专门解析 plus.md：按 ``# plus1``、``# plus2`` 等标题切分版块。

    每个 plus 版块从 ``# plusN`` 开始，直到下一个 ``# plusN+1`` 或文件结束。
    版块内部的其他 ``# `` 标题会保留在该版块内。
    """
    matches = list(re.finditer(r"\n?# plus\d+\b", markdown_text, flags=re.IGNORECASE))
    if not matches:
        return []

    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        block = markdown_text[start:end].strip()
        if not block:
            continue
        lines = block.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        sections.append((title, body))
    return sections


# --------------------------------------------------------------------------- #
# 组合构造
# --------------------------------------------------------------------------- #


def build_system_prompt(
    intro: str,
    sections: Iterable[tuple[str, str]],
    outro: str,
) -> str:
    """根据给定的段落组合构建完整系统提示词。"""
    parts = [intro]
    for title, body in sections:
        parts.append(f"{title}\n\n{body}")
    if outro:
        parts.append(outro)
    return "\n\n--------------------------------------------------\n\n".join(
        p for p in parts if p
    )


def _chinese_number_to_int(s: str) -> int | None:
    """把汉字数字（一~十）转成整数，支持简单数字。"""
    mapping = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        "〇": 0,
    }
    # 阿拉伯数字直接解析
    if s.isdigit():
        return int(s)
    # 简单汉字数字：一 ~ 十
    total = 0
    for ch in s:
        if ch in mapping:
            total += mapping[ch]
    return total if total > 0 else None


def section_id_from_title(title: str) -> str:
    """根据章节标题生成稳定的章节 ID。"""
    # 优先提取 "一、二、..." 或 "1. " 中的序号
    m = re.match(r"#\s*([一二三四五六七八九十〇\d]+)[、.\s]", title)
    if m:
        num = _chinese_number_to_int(m.group(1))
        if num is not None:
            return f"sec-{num}"
        return f"sec-{m.group(1)}"
    # 回退：使用标题前 32 个字符的 slug
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.lstrip("# ").strip())[:32]
    return f"sec-{slug}"


# --------------------------------------------------------------------------- #
# 便捷加载
# --------------------------------------------------------------------------- #


def load_skill_sections(skill_md_path: str | Path) -> dict[str, str | list[dict[str, str]]]:
    """加载 SKILL.md 并解析为章节结构。

    Returns:
        {
            "intro": str,
            "outro": str,
            "sections": [
                {"id": str, "title": str, "body": str},
                ...
            ],
            "prompt_template": str,
        }
    """
    path = Path(skill_md_path) if isinstance(skill_md_path, str) else skill_md_path
    text = path.read_text(encoding="utf-8")
    system_block = extract_system_prompt_block(text)
    intro, middle, outro = parse_sections(system_block)
    prompt_template = parse_prompt_template(text)

    return {
        "intro": intro,
        "outro": outro,
        "sections": [
            {"id": section_id_from_title(title), "title": title, "body": body}
            for title, body in middle
        ],
        "prompt_template": prompt_template,
    }


def generate_combinations(
    sections: list[tuple[str, str]],
    combination_depth: int | None = None,
    exact_depth: int | None = None,
) -> list[tuple[tuple[tuple[str, str], ...], str]]:
    """生成章节组合，返回 (组合段落列表, 组合标签)。"""
    all_combos: list[tuple[tuple[tuple[str, str], ...], str]] = []

    if exact_depth is not None:
        r = min(exact_depth, len(sections))
        for combo in combinations(sections, r):
            label = _combo_label(combo)
            all_combos.append((combo, label))
    else:
        max_r = len(sections) if combination_depth is None else min(combination_depth, len(sections))
        for r in range(1, max_r + 1):
            for combo in combinations(sections, r):
                label = _combo_label(combo)
                all_combos.append((combo, label))
    return all_combos


def _combo_label(combo: tuple[tuple[str, str], ...]) -> str:
    section_names = []
    for title, _ in combo:
        # 去掉 # 和顿号后的标题前缀，例如 "二、五感幽默系统" -> "二"
        clean = title.lstrip("# ").strip()
        m = re.match(r"([一二三四五六七八九十〇\d]+)[、.\s]", clean)
        section_names.append(m.group(1) if m else clean[:8])
    return "comb_" + "_".join(section_names)
