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
from comedy_agent.memory.models import ScriptData
from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.rag.feedback_loop import FeedbackLoop
from comedy_agent.rag.ingest import KnowledgeIngestor


def _get_memory() -> UnifiedMemory | None:
    """获取 UnifiedMemory 实例（不依赖 Orchestrator）。"""
    try:
        return UnifiedMemory()
    except Exception as e:
        print(f"\n⚠️  记忆系统初始化失败: {e}", file=sys.stderr)
        return None


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


def cmd_scripts_list(user_id: str, script_type: str | None = None) -> None:
    """列出用户的作品。"""
    memory = _get_memory()
    if memory is None:
        sys.exit(1)
    scripts = memory.list_scripts(user_id, script_type)
    if not scripts:
        print("暂无作品")
        return
    print(f"{'ID':<18} {'标题':<20} {'类型':<12} {'评分':<6} {'更新时间'}")
    print("-" * 70)
    for sc in scripts:
        title = (sc.title or "-")[:18]
        stype = sc.script_type or "-"
        rating = f"{sc.rating:.1f}" if sc.rating is not None else "-"
        updated = sc.updated_at.strftime("%Y-%m-%d %H:%M") if sc.updated_at else "-"
        print(f"{sc.script_id:<18} {title:<20} {stype:<12} {rating:<6} {updated}")


def cmd_scripts_get(script_id: str) -> None:
    """查看作品详情。"""
    memory = _get_memory()
    if memory is None:
        sys.exit(1)
    script = memory.load_script(script_id)
    if script is None:
        print(f"❌ 作品不存在: {script_id}", file=sys.stderr)
        sys.exit(1)
    print(f"作品 ID: {script.script_id}")
    print(f"标题: {script.title or '-'}")
    print(f"类型: {script.script_type or '-'}")
    print(f"评分: {script.rating if script.rating is not None else '-'}")
    print(f"标签: {', '.join(script.tags) if script.tags else '-'}")
    print(f"更新时间: {script.updated_at}")
    print("-" * 40)
    print(script.content)


def cmd_scripts_save(
    user_id: str,
    title: str,
    content: str,
    script_type: str | None = None,
    tags: list[str] | None = None,
    rating: float | None = None,
) -> None:
    """保存新作品。"""
    memory = _get_memory()
    if memory is None:
        sys.exit(1)
    script = ScriptData(
        title=title,
        content=content,
        script_type=script_type,
        tags=tags,
        rating=rating,
    )
    saved = memory.save_script(user_id, script)
    print(f"✅ 作品已保存，ID: {saved.script_id}")


def cmd_scripts_update(
    user_id: str,
    script_id: str,
    title: str | None = None,
    content: str | None = None,
    script_type: str | None = None,
    tags: list[str] | None = None,
    rating: float | None = None,
) -> None:
    """更新作品。"""
    memory = _get_memory()
    if memory is None:
        sys.exit(1)
    existing = memory.load_script(script_id)
    if existing is None:
        print(f"❌ 作品不存在: {script_id}", file=sys.stderr)
        sys.exit(1)
    updated = ScriptData(
        script_id=script_id,
        title=title if title is not None else existing.title,
        content=content if content is not None else existing.content,
        script_type=script_type if script_type is not None else existing.script_type,
        tags=tags if tags is not None else existing.tags,
        rating=rating if rating is not None else existing.rating,
    )
    memory.save_script(user_id, updated)
    print(f"✅ 作品已更新: {script_id}")


def cmd_scripts_delete(script_id: str) -> None:
    """删除作品。"""
    memory = _get_memory()
    if memory is None:
        sys.exit(1)
    ok = memory.delete_script(script_id)
    if not ok:
        print(f"❌ 作品不存在: {script_id}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ 作品已删除: {script_id}")


def cmd_scripts_rate(script_id: str, rating: float) -> None:
    """为作品评分。"""
    memory = _get_memory()
    if memory is None:
        sys.exit(1)
    ok = memory.rate_script(script_id, rating)
    if not ok:
        print(f"❌ 作品不存在: {script_id}", file=sys.stderr)
        sys.exit(1)
    print(f"✅ 评分已更新: {script_id} -> {rating}")


def cmd_feedback_loop(
    user_id: str | None = None,
    min_rating: float = 4.0,
    chunk_strategy: str = "paragraph",
    dry_run: bool = False,
) -> None:
    """将高评分剧本回流到知识库。"""
    memory = _get_memory()
    if memory is None:
        sys.exit(1)
    loop = FeedbackLoop(memory=memory, min_rating=min_rating)
    result = loop.ingest_high_rated_scripts(
        user_id=user_id,
        chunk_strategy=chunk_strategy,
        dry_run=dry_run,
    )
    if dry_run:
        print("[模拟运行] 未实际入库")
    print(f"符合条件作品: {result['ingested_scripts'] + len(result['skipped'])}")
    print(f"实际回流: {result['ingested_scripts']} 条作品，{result['total_chunks']} 个分块")
    if result["skipped"]:
        print(f"已入库跳过: {len(result['skipped'])} 条")
    if result["script_ids"]:
        print("回流作品 ID:")
        for sid in result["script_ids"]:
            print(f"  - {sid}")


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

    # scripts
    scripts_parser = subparsers.add_parser("scripts", help="用户作品管理")
    scripts_sub = scripts_parser.add_subparsers(dest="scripts_cmd", help="作品子命令")

    # scripts list
    scripts_list_parser = scripts_sub.add_parser("list", help="列出作品")
    scripts_list_parser.add_argument("--user-id", required=True, help="用户标识")
    scripts_list_parser.add_argument(
        "--type", default=None, help="作品类型过滤（standup/sketch/crosstalk/sitcom）"
    )

    # scripts get
    scripts_get_parser = scripts_sub.add_parser("get", help="查看作品详情")
    scripts_get_parser.add_argument("script_id", help="作品 ID")

    # scripts save
    scripts_save_parser = scripts_sub.add_parser("save", help="保存新作品")
    scripts_save_parser.add_argument("--user-id", required=True, help="用户标识")
    scripts_save_parser.add_argument("--title", required=True, help="作品标题")
    scripts_save_parser.add_argument("--content", required=True, help="作品内容")
    scripts_save_parser.add_argument("--type", default=None, help="作品类型")
    scripts_save_parser.add_argument("--tags", default=None, help="标签，逗号分隔")
    scripts_save_parser.add_argument("--rating", type=float, default=None, help="评分 0.0-5.0")

    # scripts update
    scripts_update_parser = scripts_sub.add_parser("update", help="更新作品")
    scripts_update_parser.add_argument("--user-id", required=True, help="用户标识")
    scripts_update_parser.add_argument("script_id", help="作品 ID")
    scripts_update_parser.add_argument("--title", default=None, help="作品标题")
    scripts_update_parser.add_argument("--content", default=None, help="作品内容")
    scripts_update_parser.add_argument("--type", default=None, help="作品类型")
    scripts_update_parser.add_argument("--tags", default=None, help="标签，逗号分隔")
    scripts_update_parser.add_argument("--rating", type=float, default=None, help="评分 0.0-5.0")

    # scripts delete
    scripts_delete_parser = scripts_sub.add_parser("delete", help="删除作品")
    scripts_delete_parser.add_argument("script_id", help="作品 ID")

    # scripts rate
    scripts_rate_parser = scripts_sub.add_parser("rate", help="为作品评分")
    scripts_rate_parser.add_argument("script_id", help="作品 ID")
    scripts_rate_parser.add_argument("rating", type=float, help="评分 0.0-5.0")

    # feedback-loop
    feedback_parser = subparsers.add_parser("feedback-loop", help="高评分内容回流到知识库")
    feedback_parser.add_argument("--user-id", default=None, help="用户标识，为空时处理所有用户")
    feedback_parser.add_argument("--min-rating", type=float, default=4.0, help="最低评分阈值")
    feedback_parser.add_argument(
        "--strategy", default="paragraph", help="分块策略（fixed/paragraph/scene/dialogue）"
    )
    feedback_parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际入库")

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
    elif args.command == "feedback-loop":
        cmd_feedback_loop(
            user_id=args.user_id,
            min_rating=args.min_rating,
            chunk_strategy=args.strategy,
            dry_run=args.dry_run,
        )
    elif args.command == "scripts":
        if args.scripts_cmd == "list":
            cmd_scripts_list(user_id=args.user_id, script_type=args.type)
        elif args.scripts_cmd == "get":
            cmd_scripts_get(script_id=args.script_id)
        elif args.scripts_cmd == "save":
            tags = args.tags.split(",") if args.tags else None
            cmd_scripts_save(
                user_id=args.user_id,
                title=args.title,
                content=args.content,
                script_type=args.type,
                tags=tags,
                rating=args.rating,
            )
        elif args.scripts_cmd == "update":
            tags = args.tags.split(",") if args.tags else None
            cmd_scripts_update(
                user_id=args.user_id,
                script_id=args.script_id,
                title=args.title,
                content=args.content,
                script_type=args.type,
                tags=tags,
                rating=args.rating,
            )
        elif args.scripts_cmd == "delete":
            cmd_scripts_delete(script_id=args.script_id)
        elif args.scripts_cmd == "rate":
            cmd_scripts_rate(script_id=args.script_id, rating=args.rating)
        else:
            scripts_parser.print_help()
            return 1
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
