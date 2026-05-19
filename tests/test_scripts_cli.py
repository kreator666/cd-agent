"""作品管理 CLI 单元测试。"""

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.api.cli import main


class TestScriptsCLI:
    """CLI 作品管理测试。"""

    @pytest.fixture
    def mock_memory(self):
        """提供内存数据库的 UnifiedMemory 实例。"""
        from comedy_agent.memory.unified import UnifiedMemory

        return UnifiedMemory(db_url="sqlite:///:memory:")

    def test_scripts_list_empty(self, capsys, mock_memory):
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            code = main(["scripts", "list", "--user-id", "u001"])
            assert code == 0
            captured = capsys.readouterr()
            assert "暂无作品" in captured.out

    def test_scripts_list_with_data(self, capsys, mock_memory):
        from comedy_agent.memory.models import ScriptData

        mock_memory.save_script(
            "u002",
            ScriptData(title="职场段子", content="加班...", script_type="standup"),
        )
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            code = main(["scripts", "list", "--user-id", "u002"])
            assert code == 0
            captured = capsys.readouterr()
            assert "职场段子" in captured.out
            assert "standup" in captured.out

    def test_scripts_list_filter_by_type(self, capsys, mock_memory):
        from comedy_agent.memory.models import ScriptData

        mock_memory.save_script(
            "u003",
            ScriptData(title="A", content="a", script_type="standup"),
        )
        mock_memory.save_script(
            "u003",
            ScriptData(title="B", content="b", script_type="sketch"),
        )
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            code = main(["scripts", "list", "--user-id", "u003", "--type", "sketch"])
            assert code == 0
            captured = capsys.readouterr()
            assert "B" in captured.out
            assert "A" not in captured.out

    def test_scripts_get_success(self, capsys, mock_memory):
        from comedy_agent.memory.models import ScriptData

        saved = mock_memory.save_script(
            "u004",
            ScriptData(title="查看我", content="内容详情"),
        )
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            code = main(["scripts", "get", saved.script_id])
            assert code == 0
            captured = capsys.readouterr()
            assert "查看我" in captured.out
            assert "内容详情" in captured.out

    def test_scripts_get_not_found(self, capsys, mock_memory):
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            with pytest.raises(SystemExit) as exc_info:
                main(["scripts", "get", "nonexistent"])
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "作品不存在" in captured.err

    def test_scripts_save_success(self, capsys, mock_memory):
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            code = main(
                [
                    "scripts",
                    "save",
                    "--user-id",
                    "u005",
                    "--title",
                    "新作品",
                    "--content",
                    "这是内容",
                    "--type",
                    "standup",
                    "--tags",
                    "职场,加班",
                    "--rating",
                    "4.5",
                ]
            )
            assert code == 0
            captured = capsys.readouterr()
            assert "作品已保存" in captured.out

        # 验证已入库
        scripts = mock_memory.list_scripts("u005")
        assert len(scripts) == 1
        assert scripts[0].title == "新作品"
        assert scripts[0].tags == ["职场", "加班"]
        assert scripts[0].rating == 4.5

    def test_scripts_update_success(self, capsys, mock_memory):
        from comedy_agent.memory.models import ScriptData

        saved = mock_memory.save_script(
            "u006",
            ScriptData(title="旧标题", content="旧内容", script_type="standup"),
        )
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            code = main(
                [
                    "scripts",
                    "update",
                    "--user-id",
                    "u006",
                    saved.script_id,
                    "--title",
                    "新标题",
                ]
            )
            assert code == 0
            captured = capsys.readouterr()
            assert "作品已更新" in captured.out

        updated = mock_memory.load_script(saved.script_id)
        assert updated is not None
        assert updated.title == "新标题"
        assert updated.content == "旧内容"
        assert updated.script_type == "standup"

    def test_scripts_update_not_found(self, capsys, mock_memory):
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            with pytest.raises(SystemExit) as exc_info:
                main(
                    [
                        "scripts",
                        "update",
                        "--user-id",
                        "u007",
                        "nonexistent",
                        "--title",
                        "X",
                    ]
                )
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "作品不存在" in captured.err

    def test_scripts_delete_success(self, capsys, mock_memory):
        from comedy_agent.memory.models import ScriptData

        saved = mock_memory.save_script(
            "u008",
            ScriptData(title="删除我", content="x"),
        )
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            code = main(["scripts", "delete", saved.script_id])
            assert code == 0
            captured = capsys.readouterr()
            assert "作品已删除" in captured.out

        assert mock_memory.load_script(saved.script_id) is None

    def test_scripts_delete_not_found(self, capsys, mock_memory):
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            with pytest.raises(SystemExit) as exc_info:
                main(["scripts", "delete", "nonexistent"])
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "作品不存在" in captured.err

    def test_scripts_rate_success(self, capsys, mock_memory):
        from comedy_agent.memory.models import ScriptData

        saved = mock_memory.save_script(
            "u009",
            ScriptData(title="评分我", content="x"),
        )
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            code = main(["scripts", "rate", saved.script_id, "4.8"])
            assert code == 0
            captured = capsys.readouterr()
            assert "评分已更新" in captured.out

        rated = mock_memory.load_script(saved.script_id)
        assert rated is not None
        assert rated.rating == 4.8

    def test_scripts_rate_not_found(self, capsys, mock_memory):
        with patch("comedy_agent.api.cli._get_memory", return_value=mock_memory):
            with pytest.raises(SystemExit) as exc_info:
                main(["scripts", "rate", "nonexistent", "5.0"])
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "作品不存在" in captured.err

    def test_scripts_memory_init_failure(self, capsys):
        with patch("comedy_agent.api.cli._get_memory", return_value=None):
            with pytest.raises(SystemExit) as exc_info:
                main(["scripts", "list", "--user-id", "u010"])
            assert exc_info.value.code == 1
