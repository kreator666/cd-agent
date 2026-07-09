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

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
DEFAULT_SKILL_MD = PROJECT_ROOT / "skills" / "standup" / "SKILL.md"
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


def parse_sections(markdown_text: str) -> tuple[str, list[tuple[str, str]], str]:
    """把系统提示词拆分为：固定开头、可选中间段落、固定结尾。

    拆分规则：
    - 按 Markdown 一级标题 ``# `` 切分。
    - 第一个一级标题之前的内容（角色定义）作为固定开头 intro。
    - 名为 ``# 十一、最终原则（最重要）`` 的段落之后、以及独立的
      ``【最终输出约束...`` 块作为固定结尾 outro。
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

    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        # 提取标题（第一行）
        lines = part.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        # 跳过最终原则段落，把它并入 outro
        if "最终原则" in title or "最终输出约束" in title:
            continue
        middle.append((title, body))

    outro = trailing_constraint
    return intro, middle, outro


def build_system_prompt(intro: str, sections: Iterable[tuple[str, str]], outro: str) -> str:
    """根据给定的段落组合构建完整系统提示词。"""
    parts = [intro]
    for title, body in sections:
        parts.append(f"{title}\n\n{body}")
    if outro:
        parts.append(outro)
    # 最后附加 skill.py 中的硬编码约束
    parts.append(OUTPUT_CONSTRAINT)
    return "\n\n--------------------------------------------------\n\n".join(parts)


def generate_template_files(
    template_dir: Path,
    intro: str,
    middle: list[tuple[str, str]],
    outro: str,
    max_combinations: int | None = None,
    combination_depth: int | None = None,
) -> list[tuple[str, Path, list[tuple[str, str]]]]:
    """生成所有排列组合模板文件，返回组合元数据列表。"""
    template_dir.mkdir(parents=True, exist_ok=True)

    # 中间段落的所有非空子集组合（按原有顺序）
    all_combos: list[tuple[tuple[str, str], ...]] = []
    max_r = len(middle) if combination_depth is None else min(combination_depth, len(middle))
    for r in range(1, max_r + 1):
        all_combos.extend(combinations(middle, r))

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
        "--user-input", type=str, default=DEFAULT_USER_INPUT,
        help="用户输入文本"
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

    # 定位 "## 系统提示词" 区块
    sys_start = skill_md_text.find("## 系统提示词")
    if sys_start == -1:
        print("错误：SKILL.md 中找不到 ## 系统提示词 区块", file=sys.stderr)
        return 1

    # 系统提示词区块以 "## 提示词模板" 结束
    sys_end = skill_md_text.find("## 提示词模板", sys_start)
    if sys_end == -1:
        system_block = skill_md_text[sys_start:]
    else:
        system_block = skill_md_text[sys_start:sys_end]

    # 去掉代码块标记（开头的 ```markdown 和结尾的 ```）
    system_block = re.sub(r"^```markdown\n?", "", system_block, flags=re.MULTILINE)
    system_block = re.sub(r"\n```\s*$", "", system_block, flags=re.MULTILINE)

    # 去掉 "## 系统提示词" 这个二级标题本身，它不属于提示词内容
    system_block = re.sub(r"^## 系统提示词\n+", "", system_block, flags=re.MULTILINE)

    intro, middle, outro = parse_sections(system_block)
    print(f"解析到固定开头 1 段，中间可组合段落 {len(middle)} 段，固定结尾 1 段。")

    if args.combination_depth is None and args.max_combinations is None:
        total_combos = 2 ** len(middle) - 1
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
        args.max_combinations,
        args.combination_depth,
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
                content = call_model(model_name, system_prompt, args.user_input)
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
