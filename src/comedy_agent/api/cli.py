"""命令行 CLI 入口。

提供交互式对话、单次运行、Skill 直接调用等能力。
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from comedy_agent import __version__
from comedy_agent.agent.orchestrator import AgentOrchestrator
from comedy_agent.models.factory import ModelConfigError
from comedy_agent.skills.standup import StandupSkill


def _build_orchestrator(model_name: str | None = None) -> AgentOrchestrator:
    """构建并初始化 Orchestrator（自动注册内置 Skill）。"""
    try:
        orch = AgentOrchestrator(model_name=model_name)
    except ModelConfigError as e:
        print(f"\n❌ 模型配置错误\n\n{e}\n", file=sys.stderr)
        sys.exit(1)
    orch.register_skill(StandupSkill())
    return orch


def cmd_version() -> None:
    """显示版本信息。"""
    print(f"Comedy Agent v{__version__}")


def cmd_skills() -> None:
    """列出所有可用 Skill。"""
    orch = _build_orchestrator()
    print("可用 Skill 列表：")
    for name in orch.list_skills():
        print(f"  - {name}")


def cmd_chat(model_name: str | None = None) -> None:
    """启动交互式对话模式。"""
    orch = _build_orchestrator(model_name=model_name)
    print("🎤 Comedy Agent 交互模式")
    print("输入你的需求（如：'写一个关于职场加班的脱口秀'），输入 exit/quit 退出\n")

    while True:
        try:
            user_input = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("再见！")
            break

        try:
            result = orch.run(user_input)
            print(f"\nAgent > {result['output']}\n")
        except Exception as e:
            print(f"\n❌ 错误: {e}\n", file=sys.stderr)


def cmd_run(prompt: str, model_name: str | None = None) -> None:
    """单次运行模式。"""
    orch = _build_orchestrator(model_name=model_name)
    result = orch.run(prompt)
    print(result["output"])


def cmd_skill_standup(topic: str, style: str, duration: int, audience: str) -> None:
    """直接调用脱口秀创作 Skill。"""
    skill = StandupSkill()
    result = skill.invoke({
        "topic": topic,
        "style": style,
        "duration": duration,
        "audience": audience,
    })
    print(result)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 主入口。"""
    parser = argparse.ArgumentParser(
        prog="comedy-agent",
        description="喜剧行业垂直 Agent CLI",
    )
    parser.add_argument(
        "--version", action="store_true", help="显示版本"
    )
    parser.add_argument(
        "--model", default=None, help="指定模型（如 gpt-4o, claude-3-5-sonnet）"
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # chat
    chat_parser = subparsers.add_parser("chat", help="启动交互式对话")
    chat_parser.add_argument("--model", default=None, help="指定模型")

    # run
    run_parser = subparsers.add_parser("run", help="单次运行")
    run_parser.add_argument("prompt", help="输入提示词")
    run_parser.add_argument("--model", default=None, help="指定模型")

    # skills
    subparsers.add_parser("skills", help="列出可用 Skill")

    # skill standup
    skill_parser = subparsers.add_parser("skill", help="直接调用 Skill")
    skill_sub = skill_parser.add_subparsers(dest="skill_name", help="Skill 名称")

    standup_parser = skill_sub.add_parser("standup", help="脱口秀创作")
    standup_parser.add_argument("--topic", required=True, help="主题")
    standup_parser.add_argument("--style", default="日常观察", help="风格")
    standup_parser.add_argument("--duration", type=int, default=3, help="时长（分钟）")
    standup_parser.add_argument("--audience", default="通用", help="受众")

    args = parser.parse_args(argv)

    if args.version:
        cmd_version()
        return 0

    # 优先使用子命令的 --model，否则使用全局 --model
    model_name = getattr(args, "model", None)

    if args.command == "chat":
        cmd_chat(model_name=model_name)
    elif args.command == "run":
        cmd_run(args.prompt, model_name=model_name)
    elif args.command == "skills":
        cmd_skills()
    elif args.command == "skill" and args.skill_name == "standup":
        cmd_skill_standup(args.topic, args.style, args.duration, args.audience)
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
