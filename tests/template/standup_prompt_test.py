#!/usr/bin/env python3
"""脱口秀系统提示词段落组合测试程序。

功能：
1. 从 skills/standup/SKILL.md 中解析系统提示词，按一级标题拆分为大段落。
2. 对中间教学段落进行排列组合，生成若干系统提示词模板，保存到 tests/template。
3. 使用固定用户输入，搭配每个提示词模板调用文生文模型。
4. 将每次调用的结果写入 tests/template/result 下的独立文件。

结果格式：
    调用哪种提示词组合：...
    调用的模型：...

    正文：
    ...

用法示例：
    python tests/template/standup_prompt_test.py
    python tests/template/standup_prompt_test.py --models ollama-qwen2.5 --max-combinations 50
    python tests/template/standup_prompt_test.py --skip-call  # 只生成模板，不调用模型
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from itertools import chain, combinations
from pathlib import Path
from typing import Iterable

from langchain_core.prompts import ChatPromptTemplate

# 把项目根目录加入路径，以便导入 comedy_agent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from comedy_agent.models.factory import ModelFactory
from comedy_agent.skills.prompt_sections import (
    build_user_input as _build_user_input,
    extract_system_prompt_block,
    parse_prompt_template,
    parse_sections,
)

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
DEFAULT_SKILL_MD = PROJECT_ROOT / "skills" / "standup" / "SKILL.md"
DEFAULT_PLUS_MD = PROJECT_ROOT / "tests" / "template" / "plus.md"
DEFAULT_TEMPLATE_DIR = PROJECT_ROOT / "tests" / "template"
DEFAULT_RESULT_DIR = PROJECT_ROOT / "tests" / "template" / "result"

# skill.py 中硬编码的最终输出约束
OUTPUT_CONSTRAINT = (
    "【最终输出约束——覆盖上述所有格式要求】\n"
    "你只允许输出段子正文，适合演员直接上台表演的内容。\n"
    "严禁输出以下任何内容：主题、人设、核心观点、使用的喜剧机制、爆点分析。\n"
    "严禁输出分析过程、思考步骤、meta说明、创作思路。\n"
    "严禁使用 Markdown 标题（如 ##）来划分输出结构。\n"
    "输出必须是连续、干净的纯文本段落，不含任何结构标签。"
)

# 默认用户输入
DEFAULT_USER_INPUT = (
    "写一段脱口秀，"
    "话题：中年危机 "
    "态度：讨厌 "
    "偏见：喝凉水都会长胖，到哪都不受待见 "
    "情绪：愤怒又无奈"
)


def parse_plus_sections(markdown_text: str) -> list[tuple[str, str]]:
    """专门解析 plus.md：按 ``# plus1``、``# plus2`` 等标题切分版块。

    每个 plus 版块从 ``# plusN`` 开始，直到下一个 ``# plusN+1`` 或文件结束。
    版块内部的其他 ``# `` 标题会保留在该版块内。
    """
    # 找到所有 # plusN 标题的位置
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


def build_system_prompt(
    intro: str,
    sections: Iterable[tuple[str, str]],
    outro: str,
    append_output_constraint: bool = True,
) -> str:
    """根据给定的段落组合构建完整系统提示词。

    复用 ``comedy_agent.skills.prompt_sections`` 的拼接逻辑，
    并额外追加测试程序所需的硬编码输出约束。
    """
    from comedy_agent.skills.prompt_sections import build_system_prompt as _base_build

    prompt = _base_build(intro, sections, outro)
    if append_output_constraint:
        prompt = prompt + "\n\n--------------------------------------------------\n\n" + OUTPUT_CONSTRAINT
    return prompt


def generate_template_files(
    template_dir: Path,
    intro: str,
    middle: list[tuple[str, str]],
    outro: str,
    plus_sections: list[tuple[str, str]] | None = None,
    max_combinations: int | None = None,
    combination_depth: int | None = None,
    exact_depth: int | None = None,
) -> list[tuple[str, Path, list[tuple[str, str]]]]:
    """生成所有排列组合模板文件，返回组合元数据列表。

    Args:
        plus_sections: 来自 plus.md 的额外可选段落，会与 middle 一起参与组合。
        exact_depth: 若指定，只生成恰好包含该数量段落的组合；
                     为 None 时生成 1..combination_depth 的所有组合。
    """
    template_dir.mkdir(parents=True, exist_ok=True)

    all_middle = list(middle)
    if plus_sections:
        all_middle.extend(plus_sections)

    # 中间段落的所有非空子集组合（按原有顺序）
    all_combos: list[tuple[tuple[str, str], ...]] = []

    if exact_depth is not None:
        r = min(exact_depth, len(all_middle))
        all_combos.extend(combinations(all_middle, r))
    else:
        max_r = len(all_middle) if combination_depth is None else min(combination_depth, len(all_middle))
        for r in range(1, max_r + 1):
            all_combos.extend(combinations(all_middle, r))

    if max_combinations is not None:
        all_combos = all_combos[:max_combinations]

    records: list[tuple[str, Path, list[tuple[str, str]]]] = []
    for idx, combo in enumerate(all_combos, start=1):
        combo_list = list(combo)
        section_names = [title.lstrip("# ").split("、")[0] for title, _ in combo_list]
        combo_label = f"comb_{idx:04d}_" + "_".join(section_names)
        system_prompt = build_system_prompt(intro, combo_list, outro)

        file_path = template_dir / f"{combo_label}.txt"
        file_path.write_text(system_prompt, encoding="utf-8")
        records.append((combo_label, file_path, combo_list))

    return records


def _escape_curly_braces(text: str) -> str:
    """把文本中的 { 和 } 转义，避免被 LangChain 当作模板变量。"""
    return text.replace("{", "{{").replace("}", "}}")


def call_model(model_name: str, system_prompt: str, user_input: str) -> str:
    """调用指定模型并返回文本结果。"""
    llm = ModelFactory.get_model(name=model_name)
    # 系统提示词和用户输入都应视为纯文本，转义其中的花括号
    prompt = ChatPromptTemplate.from_messages([
        ("system", _escape_curly_braces(system_prompt)),
        ("human", _escape_curly_braces(user_input)),
    ])
    chain = prompt | llm
    result = chain.invoke({})
    return str(result.content) if hasattr(result, "content") else str(result)


def result_file_path(
    result_dir: Path, combo_label: str, model_name: str, index: int
) -> Path:
    """构造结果文件路径。"""
    result_dir.mkdir(parents=True, exist_ok=True)
    safe_model = re.sub(r"[^\w.\-]", "_", model_name)
    return result_dir / f"{index:04d}_{combo_label}_{safe_model}.txt"


def write_result(
    result_path: Path,
    combo_label: str,
    model_name: str,
    section_titles: list[str],
    content: str,
) -> Path:
    """把单次调用结果写入独立文件。"""
    section_summary = "、".join(section_titles)
    text = (
        f"调用哪种提示词组合：{combo_label}\n"
        f"组合包含段落：{section_summary}\n"
        f"调用的模型：{model_name}\n\n"
        f"正文：\n{content}\n"
    )
    result_path.write_text(text, encoding="utf-8")
    return result_path


def main() -> int:
    parser = argparse.ArgumentParser(description="脱口秀提示词段落组合测试")
    parser.add_argument("--skill-md", type=Path, default=DEFAULT_SKILL_MD)
    parser.add_argument(
        "--plus-md",
        type=Path,
        default=None,
        help="可选的 plus.md 路径，其中的 # plus1 / # plus2 等版块会参与组合",
    )
    parser.add_argument("--template-dir", type=Path, default=DEFAULT_TEMPLATE_DIR)
    parser.add_argument("--result-dir", type=Path, default=DEFAULT_RESULT_DIR)
    parser.add_argument(
        "--models",
        type=str,
        default="",
        help="逗号分隔的模型列表，为空时使用 settings.creative_model",
    )
    parser.add_argument(
        "--max-combinations",
        type=int,
        default=None,
        help="最大组合数，默认不限制",
    )
    parser.add_argument(
        "--combination-depth",
        type=int,
        default=None,
        help="每个组合最多包含几个段落（1=单段，2=两段...），默认不限制",
    )
    parser.add_argument(
        "--exact-depth",
        type=int,
        default=None,
        help="只生成恰好包含 N 个段落的组合，避免重复生成低深度组合",
    )
    parser.add_argument(
        "--user-input", type=str, default=DEFAULT_USER_INPUT,
        help="用户输入文本"
    )
    parser.add_argument(
        "--use-prompt-template",
        action="store_true",
        help="使用 SKILL.md 中的 ## 提示词模板 格式化用户输入（与产品 loader 行为一致）",
    )
    parser.add_argument(
        "--skip-call",
        action="store_true",
        help="只生成提示词模板，不调用模型",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="每次模型调用之间的间隔秒数（限流用）",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="跳过已存在的结果文件，继续未完成的调用",
    )

    args = parser.parse_args()

    if not args.skill_md.exists():
        print(f"错误：找不到 SKILL.md 文件：{args.skill_md}", file=sys.stderr)
        return 1

    skill_md_text = args.skill_md.read_text(encoding="utf-8")

    system_block = extract_system_prompt_block(skill_md_text)
    if not system_block:
        print("错误：SKILL.md 中找不到 ## 系统提示词 区块", file=sys.stderr)
        return 1

    intro, middle, outro = parse_sections(system_block)

    # 提取 ## 提示词模板（与产品 loader 行为一致）
    prompt_template = parse_prompt_template(skill_md_text)
    if prompt_template:
        print(f"从 SKILL.md 解析到提示词模板（{len(prompt_template)} 字符）。")
    else:
        print("SKILL.md 中未找到提示词模板，将使用原始用户输入。")

    # 解析 plus.md
    plus_sections: list[tuple[str, str]] | None = None
    if args.plus_md and args.plus_md.exists():
        plus_text = args.plus_md.read_text(encoding="utf-8")
        plus_sections = parse_plus_sections(plus_text)
        print(f"从 {args.plus_md} 解析到 {len(plus_sections)} 个 plus 段落。")
    elif args.plus_md:
        print(f"警告：找不到 plus.md 文件：{args.plus_md}", file=sys.stderr)

    total_middle = len(middle) + (len(plus_sections) if plus_sections else 0)
    print(f"解析到固定开头 1 段，中间可组合段落 {total_middle} 段，固定结尾 1 段。")

    if args.exact_depth is not None:
        from math import comb
        total_combos = comb(total_middle, args.exact_depth)
        print(f"将生成恰好 {args.exact_depth} 个段落的 {total_combos} 种组合。")
    elif args.combination_depth is None and args.max_combinations is None:
        total_combos = 2 ** total_middle - 1
        print(f"将生成全部 {total_combos} 种非空组合。")
    else:
        depth_msg = f"最多 {args.combination_depth} 个段落" if args.combination_depth else "任意段落数"
        count_msg = f"最多 {args.max_combinations} 种" if args.max_combinations else "不限制数量"
        print(f"将生成 {depth_msg} 的组合，{count_msg}。")

    records = generate_template_files(
        args.template_dir,
        intro,
        middle,
        outro,
        plus_sections=plus_sections,
        max_combinations=args.max_combinations,
        combination_depth=args.combination_depth,
        exact_depth=args.exact_depth,
    )
    print(f"已生成 {len(records)} 个提示词模板到：{args.template_dir}")

    if args.skip_call:
        print("已跳过模型调用。")
        return 0

    # 解析模型列表
    from comedy_agent.core.config import settings

    if args.models:
        model_names = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        model_names = [settings.creative_model]

    print(f"将使用模型：{', '.join(model_names)}")

    # 根据 prompt_template 构建最终用户输入
    user_input = args.user_input
    if args.use_prompt_template and prompt_template:
        user_input = _build_user_input(
            args.user_input,
            prompt_template,
            extra_defaults={"section_goal": "创作一段完整的脱口秀段子", "completed_sections": "无"},
        )
        print("已使用提示词模板格式化用户输入。")

    index = 0
    for combo_label, template_path, combo_sections in records:
        system_prompt = template_path.read_text(encoding="utf-8")
        section_titles = [title for title, _ in combo_sections]

        for model_name in model_names:
            index += 1
            result_path = result_file_path(args.result_dir, combo_label, model_name, index)

            if args.resume and result_path.exists():
                print(f"[{index}] 跳过 {model_name} / {combo_label}（已存在）")
                continue

            print(f"[{index}] 调用 {model_name} / {combo_label} ...", end=" ", flush=True)
            try:
                content = call_model(model_name, system_prompt, user_input)
                write_result(result_path, combo_label, model_name, section_titles, content)
                print(f"完成 -> {result_path.name}")
            except Exception as exc:  # noqa: BLE001
                print(f"失败：{exc}")
                write_result(
                    result_path,
                    combo_label,
                    model_name,
                    section_titles,
                    f"[调用异常] {type(exc).__name__}: {exc}",
                )
                print(f"    错误结果已保存 -> {result_path.name}")

            if args.delay > 0:
                time.sleep(args.delay)

    print(f"\n全部完成，结果保存在：{args.result_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
