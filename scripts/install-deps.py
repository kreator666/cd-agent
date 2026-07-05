#!/usr/bin/env python3
"""Comedy Agent —— Python 依赖安装脚本

检查并安装项目所需的 Python 包，已安装的自动跳过。
用法:
    python scripts/install-deps.py          # 仅安装核心依赖
    python scripts/install-deps.py --dev    # 同时安装开发依赖
    python scripts/install-deps.py --ollama # 同时安装 Ollama 支持
    python scripts/install-deps.py --all    # 安装所有（核心+开发+Ollama）
"""

from __future__ import annotations

import argparse
import subprocess
import sys

# 核心依赖（必须）
CORE_DEPS = [
    "langchain>=0.2.0",
    "langchain-core>=0.2.0",
    "langchain-community>=0.2.0",
    "langchain-openai>=0.1.0",
    "langchain-anthropic>=0.1.0",
    "langgraph>=0.2.0",
    "langgraph-checkpoint-sqlite>=3.0.0",
    "chromadb>=0.5.0",
    "fastapi>=0.111.0",
    'uvicorn[standard]>=0.30.0',
    "unstructured>=0.14.0",
    "python-magic>=0.4.27",
    "pydantic>=2.7.0",
    "python-dotenv>=1.0.0",
    "httpx>=0.27.0",
    "rank-bm25>=0.2.2",
    "sentence-transformers>=3.0.0",
    "redis>=5.0.0",
    "sqlalchemy>=2.0.0",
    "alembic>=1.13.0",
    "langsmith>=0.1.0",
]

# 开发依赖（可选）
DEV_DEPS = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "black>=24.4.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
]

# 可选依赖
OPTIONAL_DEPS = {
    "ollama": ["langchain-ollama"],
}


def pip_show(package: str) -> dict[str, str] | None:
    """查询 pip 中是否已安装指定包，返回包信息或 None。"""
    # 去掉 extras 和版本号，得到纯包名
    clean_name = package.split("[")[0].split(">=")[0].split("==")[0].strip()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", clean_name],
            capture_output=True,
            text=True,
            check=True,
        )
        info: dict[str, str] = {}
        for line in result.stdout.strip().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                info[key.strip().lower()] = value.strip()
        return info
    except subprocess.CalledProcessError:
        return None


def install_package(package: str) -> bool:
    """安装单个包，返回是否成功。"""
    print(f"  ↳ 安装 {package} ...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", package],
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ 安装失败: {package} ({e})")
        return False


def check_and_install(deps: list[str]) -> tuple[list[str], list[str], list[str]]:
    """检查并安装依赖列表。

    返回: (已安装列表, 新安装成功列表, 安装失败列表)
    """
    already_installed: list[str] = []
    installed: list[str] = []
    failed: list[str] = []

    for dep in deps:
        clean_name = dep.split("[")[0].split(">=")[0].split("==")[0].strip()
        info = pip_show(dep)
        if info:
            version = info.get("version", "unknown")
            already_installed.append(f"{clean_name}=={version}")
            print(f"  ✓ {clean_name} ({version}) 已安装")
        else:
            if install_package(dep):
                installed.append(dep)
                print(f"  ✓ {dep} 安装成功")
            else:
                failed.append(dep)

    return already_installed, installed, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="安装 Comedy Agent Python 依赖")
    parser.add_argument("--dev", action="store_true", help="同时安装开发依赖")
    parser.add_argument("--ollama", action="store_true", help="同时安装 Ollama 支持")
    parser.add_argument("--all", action="store_true", help="安装所有依赖（核心+开发+可选）")
    args = parser.parse_args()

    print("=" * 60)
    print("Comedy Agent —— Python 依赖安装脚本")
    print("=" * 60)
    print(f"Python: {sys.executable}")
    print()

    # 收集需要处理的依赖
    to_install = list(CORE_DEPS)

    if args.dev or args.all:
        to_install.extend(DEV_DEPS)

    if args.ollama or args.all:
        for deps in OPTIONAL_DEPS.values():
            to_install.extend(deps)

    # 核心依赖
    print(f"[1/1] 检查并安装依赖（共 {len(to_install)} 个）...")
    already, success, failed = check_and_install(to_install)

    # 汇总
    print()
    print("-" * 60)
    print("安装汇总")
    print("-" * 60)
    print(f"  已安装跳过: {len(already)} 个")
    print(f"  本次新装:   {len(success)} 个")
    print(f"  安装失败:   {len(failed)} 个")
    if failed:
        print(f"  失败列表:   {', '.join(failed)}")
    print("-" * 60)

    if failed:
        print("\n⚠️ 部分依赖安装失败，请检查网络或手动安装。")
        return 1

    print("\n✅ 所有依赖已就绪！")
    print("   启动服务: bash scripts/start-dev.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
