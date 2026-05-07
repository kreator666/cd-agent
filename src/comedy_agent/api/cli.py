"""命令行 CLI 入口。

将在任务 1.5 中完善交互逻辑。
"""

import argparse


def main() -> None:
    """CLI 主入口。"""
    parser = argparse.ArgumentParser(description="Comedy Agent CLI")
    parser.add_argument("--version", action="store_true", help="显示版本")
    args = parser.parse_args()

    if args.version:
        from comedy_agent import __version__

        print(f"Comedy Agent v{__version__}")
    else:
        print("Comedy Agent CLI —— 更多功能即将推出")


if __name__ == "__main__":
    main()
