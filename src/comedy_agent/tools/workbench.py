"""Workbench CLI 工具 —— 封装阿里云 Workbench CLI 为 LangChain Tools。

通过 subprocess 调用 workbench CLI，支持以下操作：
- list_ecs: 按地域/状态查询 ECS 实例列表
- exec_command: 在实例上执行远程命令（结构化 JSON 输出）
- upload_file / download_file: 通过 OSS 中转传输文件
- workbench_status: 检查 CLI 安装与凭证状态

所有命令默认使用 --output json 以获得结构化输出，便于 Agent 消费。
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any, ClassVar

from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Workbench CLI 二进制路径自动检测
# ------------------------------------------------------------------ #

WORKBENCH_BIN: str | None = None


def _detect_workbench_bin() -> str | None:
    """检测 workbench CLI 二进制路径。"""
    global WORKBENCH_BIN
    if WORKBENCH_BIN is not None:
        return WORKBENCH_BIN

    # 1. 直接在 PATH 中查找
    path = shutil.which("workbench")
    if path:
        WORKBENCH_BIN = path
        return WORKBENCH_BIN

    # 2. 常见安装路径
    import platform

    system = platform.system()
    candidates: list[str] = []
    if system in ("Linux", "Darwin"):
        candidates = [
            "/usr/local/bin/workbench",
            "/opt/homebrew/bin/workbench",
        ]
    elif system == "Windows":
        program_files = (
            subprocess.check_output(
                ["echo", "%ProgramFiles%"],  # noqa: S603
                text=True,
                shell=False,
            ).strip()
            if False
            else ""
        )
        candidates = [
            r"C:\Program Files\workbench\workbench.exe",
            r"C:\Program Files (x86)\workbench\workbench.exe",
        ]

    for candidate in candidates:
        import os

        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            WORKBENCH_BIN = candidate
            return WORKBENCH_BIN

    return None


def get_workbench_bin() -> str:
    """获取 workbench 二进制路径，未安装时抛出 RuntimeError。"""
    bin_path = _detect_workbench_bin()
    if bin_path is None:
        raise RuntimeError(
            "Workbench CLI 未安装。请运行以下命令安装：\n"
            "  Linux/macOS: curl -fsSL https://workbench-cli.oss-cn-hangzhou.aliyuncs.com/install.sh | bash\n"
            "  Windows: irm https://workbench-cli.oss-cn-hangzhou.aliyuncs.com/install.ps1 | iex\n"
            "安装后执行 workbench config 配置 AccessKey。"
        )
    return bin_path


# ------------------------------------------------------------------ #
# 底层执行函数
# ------------------------------------------------------------------ #


def run_workbench_cmd(
    args: list[str],
    *,
    timeout: int = 30,
    json_output: bool = True,
) -> dict[str, Any]:
    """执行 workbench CLI 命令并返回结构化结果。

    Args:
        args: workbench 子命令及参数（不含 workbench 本身）。
        timeout: 超时秒数，默认 30。
        json_output: 是否自动追加 --output json，默认 True。

    Returns:
        dict: {
            "success": bool,
            "data": dict | str,  # JSON 解析成功时为 dict，否则为原始文本
            "exit_code": int,
            "stderr": str,
        }
    """
    bin_path = get_workbench_bin()
    cmd = [bin_path] + args
    if json_output and "--output" not in args and "-o" not in args:
        cmd.extend(["--output", "json"])

    logger.debug("执行: %s", " ".join(cmd))

    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "data": {"code": -1, "message": f"命令超时（{timeout}s）"},
            "exit_code": -1,
            "stderr": "",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "data": {"code": -2, "message": "Workbench CLI 未安装或不在 PATH 中"},
            "exit_code": -2,
            "stderr": "",
        }

    exit_code = result.returncode
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    # 尝试解析 JSON 输出
    data: dict[str, Any] | str = stdout
    if stdout:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            # 非 JSON 输出（如 text 模式），保留原始文本
            pass

    success = exit_code == 0
    if not success and isinstance(data, dict) and "message" not in data:
        data = {"code": exit_code, "message": stderr or stdout or "命令执行失败"}

    return {
        "success": success,
        "data": data,
        "exit_code": exit_code,
        "stderr": stderr,
    }


# ------------------------------------------------------------------ #
# Pydantic 参数 Schema
# ------------------------------------------------------------------ #


class ListECSArgs(BaseModel):
    """查询 ECS 实例列表参数。"""

    region: str = Field(description="阿里云地域 ID，如 cn-hangzhou")
    status: str | None = Field(default=None, description="按状态过滤: Running/Stopped/Starting/Stopping")
    tag: str | None = Field(default=None, description="按标签过滤，格式 key=value")
    instance_name: str | None = Field(default=None, description="按实例名称过滤，支持通配符 *")
    limit: int = Field(default=50, description="每页返回最大实例数，1~100")


class ExecCommandArgs(BaseModel):
    """远程命令执行参数。"""

    instance_id: str = Field(description="ECS 实例 ID")
    command: str = Field(description="要在实例上执行的命令")
    timeout: int = Field(default=30, description="命令超时时间（秒）")


class UploadFileArgs(BaseModel):
    """文件上传参数。"""

    instance_id: str = Field(description="ECS 实例 ID")
    local_path: str = Field(description="本地文件路径")
    remote_path: str = Field(description="实例上的目标路径")


class DownloadFileArgs(BaseModel):
    """文件下载参数。"""

    instance_id: str = Field(description="ECS 实例 ID")
    remote_path: str = Field(description="实例上的文件路径")
    local_path: str = Field(description="本地目标路径")


class WorkbenchStatusArgs(BaseModel):
    """Workbench CLI 状态检查（无参数）。"""

    pass


# ------------------------------------------------------------------ #
# LangChain Tool 类
# ------------------------------------------------------------------ #


class ListECSTool(BaseTool):
    """查询阿里云 ECS 实例列表。

    按地域、状态、标签等条件查询 ECS 实例，返回实例 ID、名称、IP 等信息。
    所有参数通过结构化 JSON 输出，便于 Agent 解析。
    """

    name: str = "workbench_list_ecs"
    description: str = (
        "查询阿里云 ECS 实例列表。输入地域 ID（如 cn-hangzhou），可选按状态、标签、名称过滤。"
        "返回实例 ID、名称、状态、内网 IP 等信息。"
    )
    args_schema: type[BaseModel] = ListECSArgs

    def _run(
        self,
        region: str,
        status: str | None = None,
        tag: str | None = None,
        instance_name: str | None = None,
        limit: int = 50,
    ) -> str:
        args = ["list", "ecs", "-r", region]
        if status:
            args.extend(["--status", status])
        if tag:
            args.extend(["--tag", tag])
        if instance_name:
            args.extend(["--instance-name", instance_name])
        if limit != 50:
            args.extend(["--limit", str(limit)])

        result = run_workbench_cmd(args)
        if result["success"]:
            return json.dumps(result["data"], ensure_ascii=False, indent=2)
        return f"查询失败: {result['data']}"


class ExecCommandTool(BaseTool):
    """在 ECS 实例上远程执行命令。

    在指定实例上执行一条命令并返回结果。每次调用在独立环境中执行，
    不继承上一次的 shell 状态。支持 --output json 获取结构化结果
    （output、stderr、exit_code）。
    """

    name: str = "workbench_exec"
    description: str = (
        "在阿里云 ECS 实例上执行远程命令。输入实例 ID 和要执行的命令。"
        "返回命令的标准输出、标准错误和退出码。"
    )
    args_schema: type[BaseModel] = ExecCommandArgs

    def _run(self, instance_id: str, command: str, timeout: int = 30) -> str:
        args = ["exec", "-i", instance_id, "-c", command, "--timeout", str(timeout)]
        result = run_workbench_cmd(args, timeout=timeout + 10)
        if result["success"]:
            return json.dumps(result["data"], ensure_ascii=False, indent=2)
        return f"命令执行失败: {result['data']}"


class UploadFileTool(BaseTool):
    """上传文件到 ECS 实例。

    通过 OSS 中转，在本机与实例之间传输文件。对用户完全透明，
    无需配置 OSS 权限或 Bucket。
    """

    name: str = "workbench_upload"
    description: str = (
        "上传本地文件到阿里云 ECS 实例。输入实例 ID、本地文件路径和实例上的目标路径。"
    )
    args_schema: type[BaseModel] = UploadFileArgs

    def _run(self, instance_id: str, local_path: str, remote_path: str) -> str:
        args = ["upload", local_path, remote_path, "-i", instance_id]
        result = run_workbench_cmd(args, json_output=False, timeout=120)
        if result["success"]:
            return f"上传成功: {local_path} → {instance_id}:{remote_path}"
        return f"上传失败: {result['data']}"


class DownloadFileTool(BaseTool):
    """从 ECS 实例下载文件。

    通过 OSS 中转，在实例与本机之间传输文件。对用户完全透明，
    无需配置 OSS 权限或 Bucket。
    """

    name: str = "workbench_download"
    description: str = (
        "从阿里云 ECS 实例下载文件到本地。输入实例 ID、实例上的文件路径和本地目标路径。"
    )
    args_schema: type[BaseModel] = DownloadFileArgs

    def _run(self, instance_id: str, remote_path: str, local_path: str) -> str:
        args = ["download", remote_path, local_path, "-i", instance_id]
        result = run_workbench_cmd(args, json_output=False, timeout=120)
        if result["success"]:
            return f"下载成功: {instance_id}:{remote_path} → {local_path}"
        return f"下载失败: {result['data']}"


class WorkbenchStatusTool(BaseTool):
    """检查 Workbench CLI 安装与凭证状态。

    验证 workbench CLI 是否已安装、凭证是否已配置，返回诊断信息。
    """

    name: str = "workbench_status"
    description: str = "检查阿里云 Workbench CLI 的安装状态和凭证配置。"
    args_schema: type[BaseModel] = WorkbenchStatusArgs

    def _run(self) -> str:
        bin_path = _detect_workbench_bin()
        if bin_path is None:
            return json.dumps(
                {
                    "installed": False,
                    "message": (
                        "Workbench CLI 未安装。请执行安装命令：\n"
                        "  Linux/macOS: curl -fsSL https://workbench-cli.oss-cn-hangzhou.aliyuncs.com/install.sh | bash\n"
                        "  Windows: irm https://workbench-cli.oss-cn-hangzhou.aliyuncs.com/install.ps1 | iex\n"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )

        # 检查版本
        version_result = run_workbench_cmd(["version"], json_output=False)
        version_info = version_result["data"] if version_result["success"] else "unknown"

        # 检查 daemon 状态
        daemon_result = run_workbench_cmd(["daemon", "status"], json_output=False)
        daemon_info = daemon_result["data"] if daemon_result["success"] else "not running"

        return json.dumps(
            {
                "installed": True,
                "binary_path": bin_path,
                "version": version_info,
                "daemon": daemon_info,
            },
            ensure_ascii=False,
            indent=2,
        )


# ------------------------------------------------------------------ #
# 便捷函数（非 Tool，供脚本或测试直接调用）
# ------------------------------------------------------------------ #


def list_ecs_instances(
    region: str,
    *,
    status: str | None = None,
    tag: str | None = None,
    instance_name: str | None = None,
) -> list[dict[str, Any]]:
    """查询 ECS 实例列表（便捷函数）。

    Args:
        region: 地域 ID。
        status: 可选状态过滤。
        tag: 可选标签过滤。
        instance_name: 可选名称过滤。

    Returns:
        实例信息字典列表。
    """
    args = ["list", "ecs", "-r", region]
    if status:
        args.extend(["--status", status])
    if tag:
        args.extend(["--tag", tag])
    if instance_name:
        args.extend(["--instance-name", instance_name])

    result = run_workbench_cmd(args)
    if result["success"] and isinstance(result["data"], dict):
        return result["data"].get("instances", [])
    return []


def exec_remote_command(
    instance_id: str,
    command: str,
    *,
    timeout: int = 30,
) -> dict[str, Any]:
    """在实例上执行远程命令（便捷函数）。

    Args:
        instance_id: ECS 实例 ID。
        command: 要执行的命令。
        timeout: 超时秒数。

    Returns:
        {"output": str, "stderr": str, "exit_code": int}
    """
    args = ["exec", "-i", instance_id, "-c", command, "--timeout", str(timeout)]
    result = run_workbench_cmd(args, timeout=timeout + 10)
    if result["success"] and isinstance(result["data"], dict):
        return result["data"]
    return {
        "output": "",
        "stderr": str(result["data"]),
        "exit_code": result["exit_code"],
    }


def upload_to_instance(
    instance_id: str,
    local_path: str,
    remote_path: str,
) -> bool:
    """上传文件到实例（便捷函数）。"""
    args = ["upload", local_path, remote_path, "-i", instance_id]
    result = run_workbench_cmd(args, json_output=False, timeout=120)
    return result["success"]


def download_from_instance(
    instance_id: str,
    remote_path: str,
    local_path: str,
) -> bool:
    """从实例下载文件（便捷函数）。"""
    args = ["download", remote_path, local_path, "-i", instance_id]
    result = run_workbench_cmd(args, json_output=False, timeout=120)
    return result["success"]


# ------------------------------------------------------------------ #
# 导出所有 Tool 实例（供 Agent 注册）
# ------------------------------------------------------------------ #


def get_all_workbench_tools() -> list[BaseTool]:
    """返回所有 Workbench CLI Tool 实例。"""
    return [
        WorkbenchStatusTool(),
        ListECSTool(),
        ExecCommandTool(),
        UploadFileTool(),
        DownloadFileTool(),
    ]
