"""Ollama 本地测试验证脚本。

功能：
1. 检查 Ollama 服务是否运行
2. 检查指定模型是否已下载
3. 测试 Agent / LLM 连接
4. 运行一次简单的 Skill 调用测试

用法：
    python scripts/test_ollama.py [模型名]

示例：
    python scripts/test_ollama.py ollama-llama3
    python scripts/test_ollama.py ollama-qwen2.5
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
import json


def check_ollama_service(host: str = "http://localhost:11434") -> bool:
    """检查 Ollama 服务是否运行。"""
    try:
        req = urllib.request.Request(
            f"{host}/api/tags",
            method="GET",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_local_models(host: str = "http://localhost:11434") -> list[str]:
    """获取本地已下载的模型列表。"""
    try:
        req = urllib.request.Request(
            f"{host}/api/tags",
            method="GET",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def check_model_available(model_name: str, host: str = "http://localhost:11434") -> bool:
    """检查指定模型是否已下载到本地。"""
    local_models = list_local_models(host)
    # Ollama API 返回的模型名可能带 :tag 后缀（如 :latest, :7b）
    return any(
        model_name == m
        or model_name == m.split(":")[0]
        or model_name == m.replace(":latest", "")
        for m in local_models
    )


def resolve_ollama_model_name(model_name: str, host: str = "http://localhost:11434") -> str:
    """解析并返回本地精确匹配的 Ollama 模型名。

    如果用户指定了不带 tag 的模型名（如 qwen2.5），但本地只有带 tag 的版本
    （如 qwen2.5:7b），则返回带 tag 的完整名称，以便 ChatOllama 能正确调用。
    """
    if not model_name.startswith("ollama-"):
        return model_name

    ollama_id = model_name.replace("ollama-", "")
    local_models = list_local_models(host)

    # 精确匹配
    if ollama_id in local_models:
        return model_name

    # 模糊匹配：qwen2.5 -> qwen2.5:7b
    for m in local_models:
        base_name = m.split(":")[0]
        if ollama_id == base_name or ollama_id == m.replace(":latest", ""):
            return f"ollama-{m}"

    return model_name


def test_llm_connection(model_name: str) -> bool:
    """测试 LLM 连接，尝试一次简单调用。"""
    try:
        from comedy_agent.models.factory import ModelFactory

        print(f"  → 正在加载模型 '{model_name}'...")
        llm = ModelFactory.get_model(model_name)
        print(f"  → 模型实例: {type(llm).__name__}")

        print("  → 发送测试消息 '你好，请回复：Ollama 连接成功'...")
        response = llm.invoke("你好，请回复：Ollama 连接成功")
        content = response.content if hasattr(response, "content") else str(response)
        print(f"  → 收到回复: {content.strip()[:100]}")
        return True
    except Exception as e:
        print(f"  [FAIL] LLM 测试失败: {e}")
        return False


def test_agent_orchestrator(model_name: str) -> bool:
    """测试 Agent Orchestrator 能否正常工作。"""
    try:
        from comedy_agent.agent.orchestrator import AgentOrchestrator
        from comedy_agent.skills.standup import StandupSkill

        print(f"  → 初始化 AgentOrchestrator (model={model_name})...")
        orch = AgentOrchestrator(model_name=model_name)
        orch.register_skill(StandupSkill())
        print(f"  → 已注册 Skills: {orch.list_skills()}")

        print("  → 运行测试任务: '讲个笑话'...")
        result = orch.run("讲个笑话")
        output = result.get("output", "")
        print(f"  → Agent 输出:\n{'─' * 50}")
        print(output.strip()[:500] if output else "(空输出)")
        print(f"{'─' * 50}")
        return bool(output)
    except Exception as e:
        print(f"  [FAIL] Agent 测试失败: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Ollama 本地测试验证")
    parser.add_argument(
        "model",
        nargs="?",
        default="ollama-llama3",
        help="要测试的模型名称（默认: ollama-llama3）",
    )
    parser.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama 服务地址（默认: http://localhost:11434）",
    )
    args = parser.parse_args()

    model_name = args.model
    # 提取 ollama 实际的模型 ID（去掉 ollama- 前缀）
    ollama_model_id = model_name.replace("ollama-", "") if model_name.startswith("ollama-") else model_name

    print("=" * 60)
    print("Ollama 本地测试验证")
    print("=" * 60)

    # 1. 检查 Ollama 服务
    print("\n[1/4] 检查 Ollama 服务状态...")
    if check_ollama_service(args.host):
        print("  [OK] Ollama 服务正在运行")
    else:
        print("  [FAIL] Ollama 服务未启动或无法连接")
        print(f"\n  [HINT] 请执行以下命令启动服务：")
        print(f"     ollama serve")
        print(f"\n  或下载安装：https://ollama.com/download")
        return 1

    # 2. 检查模型是否已下载，并解析精确模型名
    print(f"\n[2/4] 检查模型 '{ollama_model_id}' 是否已下载...")
    local_models = list_local_models(args.host)
    if local_models:
        print(f"  本地已有模型: {', '.join(local_models)}")
    else:
        print("  本地暂无模型")

    if not check_model_available(ollama_model_id, args.host):
        print(f"  [FAIL] 模型 '{ollama_model_id}' 未下载")
        print(f"\n  [HINT] 请执行以下命令拉取模型：")
        print(f"     ollama pull {ollama_model_id}")
        return 1

    # 自动解析带 tag 的完整模型名（如 qwen2.5 -> qwen2.5:7b）
    resolved_name = resolve_ollama_model_name(model_name, args.host)
    if resolved_name != model_name:
        print(f"  [OK] 模型 '{ollama_model_id}' 已就绪")
        print(f"  [INFO] 自动解析为精确模型名: {resolved_name}")
        model_name = resolved_name
    else:
        print(f"  [OK] 模型 '{ollama_model_id}' 已就绪")

    # 3. 测试 LLM 连接
    print(f"\n[3/4] 测试 LLM 连接 (model={model_name})...")
    if not test_llm_connection(model_name):
        return 1
    print("  [OK] LLM 连接测试通过")

    # 4. 测试 Agent Orchestrator
    print(f"\n[4/4] 测试 Agent Orchestrator...")
    if not test_agent_orchestrator(model_name):
        return 1
    print("  [OK] Agent 测试通过")

    print("\n" + "=" * 60)
    print("[SUCCESS] 全部测试通过！你可以开始使用 Ollama 本地测试 Agent 了。")
    print("=" * 60)
    print("\n常用命令：")
    print(f"  交互对话:  python -m comedy_agent chat --model {model_name}")
    print(f"  单次运行:  python -m comedy_agent run \"讲个笑话\" --model {model_name}")
    print(f"  列出模型:  ollama list")
    print(f"  拉取模型:  ollama pull <model>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
