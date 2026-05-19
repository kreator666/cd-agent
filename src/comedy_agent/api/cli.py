"""命令行 CLI 入口。

提供交互式对话、单次运行、Skill 直接调用等能力。
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from comedy_agent import __version__
from comedy_agent.agent.orchestrator import AgentOrchestrator
from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.models.factory import ModelConfigError
from comedy_agent.skills import (
    CrosstalkSkill,
    JokeAnalyzerSkill,
    ScriptEvaluatorSkill,
    SitcomSkill,
    SketchSkill,
    StandupSkill,
)
from comedy_agent.skills.loader import load_plugin_skills
from comedy_agent.core.prompt_manager import PromptManager
from comedy_agent.rag.ingest import KnowledgeIngestor


def _build_orchestrator(
    model_name: str | None = None,
    user_id: str | None = None,
) -> tuple[AgentOrchestrator, str | None]:
    """构建并初始化 Orchestrator（自动加载 Prompt、Memory 与 Skill）。

    Returns:
        tuple: (Orchestrator 实例, user_id)
    """
    try:
        memory = UnifiedMemory()
    except Exception as e:
        print(f"\n⚠️  记忆系统初始化失败: {e}", file=sys.stderr)
        memory = None

    try:
        orch = AgentOrchestrator(model_name=model_name, memory=memory)
    except ModelConfigError as e:
        print(f"\n❌ 模型配置错误\n\n{e}\n", file=sys.stderr)
        sys.exit(1)
    orch.register_skill(StandupSkill())
    orch.register_skill(CrosstalkSkill())
    orch.register_skill(SketchSkill())
    orch.register_skill(SitcomSkill())
    orch.register_skill(JokeAnalyzerSkill())
    orch.register_skill(ScriptEvaluatorSkill())

    # 加载外部插件 Skill
    for plugin in load_plugin_skills():
        orch.register_skill(plugin)

    return orch, user_id


def cmd_version() -> None:
    """显示版本信息。"""
    print(f"Comedy Agent v{__version__}")


def _print_runtime_error(e: Exception) -> None:
    """打印友好的运行时错误提示。"""
    err_msg = str(e).lower()
    if "responseerror" in err_msg or "status code: 502" in err_msg:
        print(
            "\n❌ 无法连接到 Ollama 服务。\n"
            "请先安装并启动 Ollama：\n"
            "  1. 下载安装：https://ollama.com/download\n"
            "  2. 启动服务：ollama serve\n"
            "  3. 拉取模型：ollama pull llama3\n"
            "或使用云端模型：--model gpt-4o / claude-3-5-sonnet\n",
            file=sys.stderr,
        )
    elif "status code: 404" in err_msg or "not found" in err_msg:
        print(
            "\n❌ Ollama 模型未找到。\n"
            "可能的原因和解决方案：\n"
            "  1. 模型尚未拉取：ollama pull llama3\n"
            "  2. 模型名称拼写错误，查看已安装模型：ollama list\n"
            "  3. 使用其他模型：--model ollama-qwen2.5 / ollama-llama3.1\n"
            "或使用云端模型：--model gpt-4o / claude-3-5-sonnet\n",
            file=sys.stderr,
        )
    elif "does not support tools" in err_msg or "status code: 400" in err_msg:
        print(
            "\n❌ Ollama 模型不支持 Tool 调用。\n"
            "Comedy Agent 的交互模式需要模型支持 Tool/Function Calling。\n"
            "解决方案：\n"
            "  1. 换用支持 Tool 的模型：ollama pull llama3.1\n"
            "  2. 或换用：ollama pull qwen2.5\n"
            "  3. 使用云端模型：--model gpt-4o / claude-3-5-sonnet\n"
            "注意：llama3（非 3.1 版）不支持 Tool Calling。\n",
            file=sys.stderr,
        )
    else:
        print(f"\n❌ 错误: {e}\n", file=sys.stderr)


def cmd_skills() -> None:
    """列出所有可用 Skill。"""
    orch, _ = _build_orchestrator()
    print("可用 Skill 列表：")
    for name in orch.list_skills():
        print(f"  - {name}")


def cmd_chat(model_name: str | None = None, user_id: str | None = None) -> None:
    """启动交互式对话模式。"""
    orch, uid = _build_orchestrator(model_name=model_name, user_id=user_id)
    print("🎤 Comedy Agent 交互模式")
    if uid:
        print(f"当前用户: {uid}")
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
            result = orch.run(user_input, user_id=uid)
            print(f"\nAgent > {result['output']}\n")
        except Exception as e:
            _print_runtime_error(e)


def cmd_run(prompt: str, model_name: str | None = None, user_id: str | None = None) -> None:
    """单次运行模式。"""
    orch, uid = _build_orchestrator(model_name=model_name, user_id=user_id)
    try:
        result = orch.run(prompt, user_id=uid)
        print(result["output"])
    except Exception as e:
        _print_runtime_error(e)
        sys.exit(1)


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


def cmd_ingest(dir_path: str | None = None) -> None:
    """导入知识库数据。"""
    try:
        ingestor = KnowledgeIngestor()
        result = ingestor.ingest_directory(dir_path)
        print(f"导入完成：")
        print(f"  原始文档: {result['raw_docs']}")
        print(f"  分块数量: {result['chunks']}")
        print(f"  入库文档: {result['ingested']}")
        print(f"  集合名称: {result['collection']}")
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 导入失败: {e}", file=sys.stderr)
        sys.exit(1)


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
    chat_parser.add_argument("--user-id", default=None, help="用户标识，用于注入记忆上下文")

    # run
    run_parser = subparsers.add_parser("run", help="单次运行")
    run_parser.add_argument("prompt", help="输入提示词")
    run_parser.add_argument("--model", default=None, help="指定模型")
    run_parser.add_argument("--user-id", default=None, help="用户标识，用于注入记忆上下文")

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

    # ingest
    ingest_parser = subparsers.add_parser("ingest", help="导入知识库数据")
    ingest_parser.add_argument("--dir", default=None, help="知识库目录路径")

    args = parser.parse_args(argv)

    if args.version:
        cmd_version()
        return 0

    # 优先使用子命令的 --model，否则使用全局 --model
    model_name = getattr(args, "model", None)

    user_id = getattr(args, "user_id", None)

    if args.command == "chat":
        cmd_chat(model_name=model_name, user_id=user_id)
    elif args.command == "run":
        cmd_run(args.prompt, model_name=model_name, user_id=user_id)
    elif args.command == "skills":
        cmd_skills()
    elif args.command == "skill" and args.skill_name == "standup":
        cmd_skill_standup(args.topic, args.style, args.duration, args.audience)
    elif args.command == "ingest":
        cmd_ingest(dir_path=args.dir)
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
