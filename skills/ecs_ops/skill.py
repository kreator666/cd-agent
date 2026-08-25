"""阿里云 ECS 远程运维 Skill —— 通过 Workbench CLI 管理 ECS 实例。"""

from typing import Any

from pydantic import BaseModel, Field

from comedy_agent.skills.base import ComedySkill


class ECSOpsArgs(BaseModel):
    """ECS 运维操作参数。"""

    action: str = Field(
        description="操作类型: list(查询实例)/exec(执行命令)/upload(上传文件)/download(下载文件)/status(检查状态)"
    )
    region: str = Field(default="cn-hangzhou", description="阿里云地域 ID")
    instance_id: str = Field(default="", description="ECS 实例 ID（exec/upload/download 必填）")
    command: str = Field(default="", description="要执行的远程命令（exec 必填）")
    local_path: str = Field(default="", description="本地文件路径（upload/download 需要）")
    remote_path: str = Field(default="", description="实例上的文件路径（upload/download 需要）")
    status_filter: str = Field(default="", description="按状态过滤: Running/Stopped/Starting/Stopping")


class Skill(ComedySkill):
    """阿里云 ECS 远程运维 Skill。"""

    task_type: str = "fast"
    name: str = "ecs_ops"
    description: str = (
        "阿里云 ECS 云服务器远程运维。通过 Workbench CLI 免密连接无公网 IP 的 Linux 实例，"
        "支持实例查询、远程命令执行、文件传输。"
    )
    args_schema: type[BaseModel] = ECSOpsArgs

    SYSTEM_PROMPT: str = (
        "你是一位阿里云 ECS 运维专家。通过 Workbench CLI 工具管理云服务器实例。"
        "所有命令默认使用 --output json 获取结构化输出。"
        "遇到错误时根据错误类型决定是否重试。"
    )

    def _run(
        self,
        action: str,
        region: str = "cn-hangzhou",
        instance_id: str = "",
        command: str = "",
        local_path: str = "",
        remote_path: str = "",
        status_filter: str = "",
    ) -> str:
        from comedy_agent.tools.workbench import (
            list_ecs_instances,
            exec_remote_command,
            upload_to_instance,
            download_from_instance,
            run_workbench_cmd,
        )
        import json

        action = action.lower().strip()

        if action == "status":
            from comedy_agent.tools.workbench import get_workbench_bin, _detect_workbench_bin

            bin_path = _detect_workbench_bin()
            if bin_path is None:
                return json.dumps(
                    {"installed": False, "message": "Workbench CLI 未安装"},
                    ensure_ascii=False,
                )
            version_result = run_workbench_cmd(["version"], json_output=False)
            return json.dumps(
                {
                    "installed": True,
                    "binary_path": bin_path,
                    "version": version_result["data"] if version_result["success"] else "unknown",
                },
                ensure_ascii=False,
                indent=2,
            )

        elif action == "list":
            instances = list_ecs_instances(
                region,
                status=status_filter if status_filter else None,
            )
            return json.dumps(
                {"region": region, "count": len(instances), "instances": instances},
                ensure_ascii=False,
                indent=2,
            )

        elif action == "exec":
            if not instance_id:
                return "错误：exec 操作需要提供 instance_id"
            if not command:
                return "错误：exec 操作需要提供 command"
            result = exec_remote_command(instance_id, command)
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif action == "upload":
            if not instance_id:
                return "错误：upload 操作需要提供 instance_id"
            if not local_path:
                return "错误：upload 操作需要提供 local_path"
            if not remote_path:
                return "错误：upload 操作需要提供 remote_path"
            success = upload_to_instance(instance_id, local_path, remote_path)
            return (
                f"上传成功: {local_path} → {instance_id}:{remote_path}"
                if success
                else f"上传失败: {local_path} → {instance_id}:{remote_path}"
            )

        elif action == "download":
            if not instance_id:
                return "错误：download 操作需要提供 instance_id"
            if not remote_path:
                return "错误：download 操作需要提供 remote_path"
            if not local_path:
                return "错误：download 操作需要提供 local_path"
            success = download_from_instance(instance_id, remote_path, local_path)
            return (
                f"下载成功: {instance_id}:{remote_path} → {local_path}"
                if success
                else f"下载失败: {instance_id}:{remote_path} → {local_path}"
            )

        else:
            return f"未知操作类型: {action}。支持的操作: list, exec, upload, download, status"

    async def _arun(
        self,
        action: str,
        region: str = "cn-hangzhou",
        instance_id: str = "",
        command: str = "",
        local_path: str = "",
        remote_path: str = "",
        status_filter: str = "",
        **kwargs: Any,
    ) -> str:
        return self._run(
            action=action,
            region=region,
            instance_id=instance_id,
            command=command,
            local_path=local_path,
            remote_path=remote_path,
            status_filter=status_filter,
        )
