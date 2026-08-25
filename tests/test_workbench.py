"""Workbench CLI 工具测试。

测试 workbench 模块的各个组件，包括：
- 二进制路径检测
- 命令执行与 JSON 解析
- LangChain Tool 类
- 便捷函数
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, mock_open

import pytest

from comedy_agent.tools.workbench import (
    _detect_workbench_bin,
    get_workbench_bin,
    run_workbench_cmd,
    ListECSTool,
    ExecCommandTool,
    UploadFileTool,
    DownloadFileTool,
    WorkbenchStatusTool,
    list_ecs_instances,
    exec_remote_command,
    upload_to_instance,
    download_from_instance,
    get_all_workbench_tools,
    WORKBENCH_BIN,
)


# ------------------------------------------------------------------ #
# 二进制路径检测
# ------------------------------------------------------------------ #


class TestDetectWorkbenchBin:
    """测试 workbench 二进制路径检测。"""

    def setup_method(self):
        """重置全局缓存。"""
        import comedy_agent.tools.workbench as wb
        wb.WORKBENCH_BIN = None

    def teardown_method(self):
        """重置全局缓存。"""
        import comedy_agent.tools.workbench as wb
        wb.WORKBENCH_BIN = None

    @patch("shutil.which", return_value="/usr/local/bin/workbench")
    def test_detect_from_path(self, mock_which):
        """从 PATH 检测到 workbench。"""
        result = _detect_workbench_bin()
        assert result == "/usr/local/bin/workbench"
        mock_which.assert_called_once_with("workbench")

    @patch("shutil.which", return_value=None)
    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    def test_detect_from_common_path(self, mock_access, mock_isfile, mock_which):
        """从常见安装路径检测到 workbench。"""
        result = _detect_workbench_bin()
        assert result is not None
        # 应该检查了至少一个常见路径
        assert mock_isfile.call_count >= 1

    @patch("shutil.which", return_value=None)
    @patch("os.path.isfile", return_value=False)
    def test_detect_not_found(self, mock_isfile, mock_which):
        """未找到 workbench 时返回 None。"""
        result = _detect_workbench_bin()
        assert result is None

    @patch("shutil.which", return_value="/usr/local/bin/workbench")
    def test_detect_caches_result(self, mock_which):
        """检测结果会被缓存。"""
        result1 = _detect_workbench_bin()
        result2 = _detect_workbench_bin()
        assert result1 == result2
        # 第二次调用不应该再调用 shutil.which
        mock_which.assert_called_once()

    def test_get_workbench_bin_raises_when_not_installed(self):
        """未安装时 get_workbench_bin 抛出 RuntimeError。"""
        import comedy_agent.tools.workbench as wb
        wb.WORKBENCH_BIN = None
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            with pytest.raises(RuntimeError, match="未安装"):
                get_workbench_bin()

    @patch("shutil.which", return_value="/usr/local/bin/workbench")
    def test_get_workbench_bin_returns_path(self, mock_which):
        """已安装时 get_workbench_bin 返回路径。"""
        result = get_workbench_bin()
        assert result == "/usr/local/bin/workbench"


# ------------------------------------------------------------------ #
# 命令执行
# ------------------------------------------------------------------ #


class TestRunWorkbenchCmd:
    """测试 workbench 命令执行。"""

    def setup_method(self):
        import comedy_agent.tools.workbench as wb
        wb.WORKBENCH_BIN = "/usr/local/bin/workbench"

    def teardown_method(self):
        import comedy_agent.tools.workbench as wb
        wb.WORKBENCH_BIN = None

    @patch("subprocess.run")
    def test_successful_json_output(self, mock_run):
        """成功执行命令并返回 JSON 输出。"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"instances": [{"instance_id": "i-abc"}]}',
            stderr="",
        )
        result = run_workbench_cmd(["list", "ecs", "-r", "cn-hangzhou"])
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert isinstance(result["data"], dict)
        assert "instances" in result["data"]

    @patch("subprocess.run")
    def test_successful_text_output(self, mock_run):
        """成功执行命令返回文本输出。"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="workbench version 1.0.0",
            stderr="",
        )
        result = run_workbench_cmd(["version"], json_output=False)
        assert result["success"] is True
        assert result["data"] == "workbench version 1.0.0"

    @patch("subprocess.run")
    def test_failed_command(self, mock_run):
        """命令执行失败。"""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='{"code": 1, "message": "InvalidAccessKeyId"}',
            stderr="Error",
        )
        result = run_workbench_cmd(["list", "ecs", "-r", "cn-hangzhou"])
        assert result["success"] is False
        assert result["exit_code"] == 1

    @patch("subprocess.run")
    def test_timeout(self, mock_run):
        """命令超时。"""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="workbench", timeout=30)
        result = run_workbench_cmd(["exec", "-i", "i-xxx", "-c", "sleep 60"])
        assert result["success"] is False
        assert result["exit_code"] == -1
        assert "超时" in result["data"]["message"]

    @patch("subprocess.run")
    def test_command_not_found(self, mock_run):
        """workbench 二进制不存在。"""
        mock_run.side_effect = FileNotFoundError
        result = run_workbench_cmd(["version"])
        assert result["success"] is False
        assert result["exit_code"] == -2
        assert "未安装" in result["data"]["message"]

    @patch("subprocess.run")
    def test_auto_adds_json_output(self, mock_run):
        """自动追加 --output json 参数。"""
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        run_workbench_cmd(["list", "ecs", "-r", "cn-hangzhou"])
        cmd_args = mock_run.call_args[0][0]
        assert "--output" in cmd_args
        assert "json" in cmd_args

    @patch("subprocess.run")
    def test_no_duplicate_json_output(self, mock_run):
        """不重复追加 --output json。"""
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        run_workbench_cmd(["list", "ecs", "-r", "cn-hangzhou", "--output", "json"])
        cmd_args = mock_run.call_args[0][0]
        # 只应有一个 --output
        assert cmd_args.count("--output") == 1


# ------------------------------------------------------------------ #
# LangChain Tool 类
# ------------------------------------------------------------------ #


class TestListECSTool:
    """测试 ListECSTool。"""

    def test_tool_metadata(self):
        """检查 Tool 元数据。"""
        tool = ListECSTool()
        assert tool.name == "workbench_list_ecs"
        assert "ECS" in tool.description or "ecs" in tool.description.lower()

    def test_tool_args_schema(self):
        """检查参数 Schema。"""
        tool = ListECSTool()
        schema = tool.args_schema
        fields = schema.model_fields
        assert "region" in fields
        assert "status" in fields
        assert "tag" in fields

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_run_success(self, mock_cmd):
        """成功执行查询。"""
        mock_cmd.return_value = {
            "success": True,
            "data": {"instances": [{"instance_id": "i-abc", "status": "Running"}]},
            "exit_code": 0,
            "stderr": "",
        }
        tool = ListECSTool()
        result = tool._run(region="cn-hangzhou", status="Running")
        parsed = json.loads(result)
        assert "instances" in parsed
        assert len(parsed["instances"]) == 1

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_run_failure(self, mock_cmd):
        """查询失败。"""
        mock_cmd.return_value = {
            "success": False,
            "data": {"code": 1, "message": "NoPermission"},
            "exit_code": 1,
            "stderr": "",
        }
        tool = ListECSTool()
        result = tool._run(region="cn-hangzhou")
        assert "失败" in result


class TestExecCommandTool:
    """测试 ExecCommandTool。"""

    def test_tool_metadata(self):
        tool = ExecCommandTool()
        assert tool.name == "workbench_exec"
        assert "exec" in tool.description.lower() or "执行" in tool.description

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_run_success(self, mock_cmd):
        """成功执行远程命令。"""
        mock_cmd.return_value = {
            "success": True,
            "data": {"output": "hello\n", "stderr": "", "exit_code": 0},
            "exit_code": 0,
            "stderr": "",
        }
        tool = ExecCommandTool()
        result = tool._run(instance_id="i-abc123", command="echo hello")
        parsed = json.loads(result)
        assert parsed["output"] == "hello\n"
        assert parsed["exit_code"] == 0


class TestUploadFileTool:
    """测试 UploadFileTool。"""

    def test_tool_metadata(self):
        tool = UploadFileTool()
        assert tool.name == "workbench_upload"

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_run_success(self, mock_cmd):
        mock_cmd.return_value = {"success": True, "data": "", "exit_code": 0, "stderr": ""}
        tool = UploadFileTool()
        result = tool._run(instance_id="i-abc", local_path="/tmp/test.txt", remote_path="/opt/test.txt")
        assert "上传成功" in result


class TestDownloadFileTool:
    """测试 DownloadFileTool。"""

    def test_tool_metadata(self):
        tool = DownloadFileTool()
        assert tool.name == "workbench_download"

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_run_success(self, mock_cmd):
        mock_cmd.return_value = {"success": True, "data": "", "exit_code": 0, "stderr": ""}
        tool = DownloadFileTool()
        result = tool._run(instance_id="i-abc", remote_path="/opt/test.txt", local_path="/tmp/test.txt")
        assert "下载成功" in result


class TestWorkbenchStatusTool:
    """测试 WorkbenchStatusTool。"""

    def test_tool_metadata(self):
        tool = WorkbenchStatusTool()
        assert tool.name == "workbench_status"

    def test_run_not_installed(self):
        """未安装时返回状态。"""
        import comedy_agent.tools.workbench as wb
        wb.WORKBENCH_BIN = None
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            tool = WorkbenchStatusTool()
            result = tool._run()
            parsed = json.loads(result)
            assert parsed["installed"] is False

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_run_installed(self, mock_cmd):
        """已安装时返回状态。"""
        import comedy_agent.tools.workbench as wb
        wb.WORKBENCH_BIN = "/usr/local/bin/workbench"
        mock_cmd.return_value = {
            "success": True,
            "data": "workbench version 1.0.0",
            "exit_code": 0,
            "stderr": "",
        }
        tool = WorkbenchStatusTool()
        result = tool._run()
        parsed = json.loads(result)
        assert parsed["installed"] is True
        assert "binary_path" in parsed


# ------------------------------------------------------------------ #
# 便捷函数
# ------------------------------------------------------------------ #


class TestConvenienceFunctions:
    """测试便捷函数。"""

    def setup_method(self):
        import comedy_agent.tools.workbench as wb
        wb.WORKBENCH_BIN = "/usr/local/bin/workbench"

    def teardown_method(self):
        import comedy_agent.tools.workbench as wb
        wb.WORKBENCH_BIN = None

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_list_ecs_instances(self, mock_cmd):
        """查询实例列表。"""
        mock_cmd.return_value = {
            "success": True,
            "data": {"instances": [{"instance_id": "i-abc"}]},
            "exit_code": 0,
            "stderr": "",
        }
        instances = list_ecs_instances("cn-hangzhou", status="Running")
        assert len(instances) == 1
        assert instances[0]["instance_id"] == "i-abc"

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_list_ecs_instances_failure(self, mock_cmd):
        """查询失败返回空列表。"""
        mock_cmd.return_value = {
            "success": False,
            "data": {"code": 1, "message": "error"},
            "exit_code": 1,
            "stderr": "",
        }
        instances = list_ecs_instances("cn-hangzhou")
        assert instances == []

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_exec_remote_command(self, mock_cmd):
        """执行远程命令。"""
        mock_cmd.return_value = {
            "success": True,
            "data": {"output": "ok", "stderr": "", "exit_code": 0},
            "exit_code": 0,
            "stderr": "",
        }
        result = exec_remote_command("i-abc", "echo ok")
        assert result["output"] == "ok"
        assert result["exit_code"] == 0

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_upload_to_instance(self, mock_cmd):
        """上传文件。"""
        mock_cmd.return_value = {"success": True, "data": "", "exit_code": 0, "stderr": ""}
        assert upload_to_instance("i-abc", "/tmp/a.txt", "/opt/a.txt") is True

    @patch("comedy_agent.tools.workbench.run_workbench_cmd")
    def test_download_from_instance(self, mock_cmd):
        """下载文件。"""
        mock_cmd.return_value = {"success": True, "data": "", "exit_code": 0, "stderr": ""}
        assert download_from_instance("i-abc", "/opt/a.txt", "/tmp/a.txt") is True


# ------------------------------------------------------------------ #
# get_all_workbench_tools
# ------------------------------------------------------------------ #


class TestGetAllWorkbenchTools:
    """测试工具集合导出。"""

    def test_returns_all_tools(self):
        """返回所有工具实例。"""
        tools = get_all_workbench_tools()
        assert len(tools) == 5
        names = {t.name for t in tools}
        assert "workbench_status" in names
        assert "workbench_list_ecs" in names
        assert "workbench_exec" in names
        assert "workbench_upload" in names
        assert "workbench_download" in names

    def test_all_are_langchain_tools(self):
        """所有工具都是 LangChain BaseTool 实例。"""
        from langchain_core.tools import BaseTool as LCTool
        tools = get_all_workbench_tools()
        for tool in tools:
            assert isinstance(tool, LCTool)
