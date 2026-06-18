"""CLI 单元测试。"""

from unittest.mock import MagicMock, patch

import pytest

from comedy_agent.api.cli import main


class TestCLI:
    """测试命令行接口。"""

    def test_version(self, capsys):
        """--version 输出版本号。"""
        code = main(["--version"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Comedy Agent" in captured.out
        assert "0.1.0" in captured.out

    def test_no_args_prints_help(self, capsys):
        """无参数时打印帮助。"""
        code = main([])
        assert code == 1
        captured = capsys.readouterr()
        assert "usage:" in captured.out

    def test_skills_list(self, capsys):
        """skills 子命令列出 Skill。"""
        with patch(
            "comedy_agent.api.cli._build_orchestrator"
        ) as mock_build:
            mock_orch = MagicMock()
            mock_orch.list_skills.return_value = ["standup_generator"]
            mock_build.return_value = (mock_orch, None)

            code = main(["skills"])

            assert code == 0
            captured = capsys.readouterr()
            assert "standup_generator" in captured.out

    def test_run_single_prompt(self, capsys):
        """run 子命令单次执行。"""
        with patch(
            "comedy_agent.api.cli._build_orchestrator"
        ) as mock_build:
            mock_orch = MagicMock()
            mock_orch.run.return_value = {"output": "测试输出"}
            mock_build.return_value = (mock_orch, None)

            code = main(["run", "写一个段子"])

            assert code == 0
            captured = capsys.readouterr()
            assert "测试输出" in captured.out
            mock_orch.run.assert_called_once_with("写一个段子", user_id=None)

    def test_skill_standup(self, capsys):
        """skill standup 直接调用 Skill。"""
        with patch(
            "comedy_agent.api.cli.load_single_skill"
        ) as mock_loader:
            mock_skill = MagicMock()
            mock_skill.invoke.return_value = "段子内容"
            mock_loader.return_value = mock_skill

            code = main([
                "skill", "standup",
                "--topic", "职场",
                "--style", "自嘲",
                "--duration", "5",
                "--audience", "互联网人",
            ])

            assert code == 0
            captured = capsys.readouterr()
            assert "段子内容" in captured.out
            mock_skill.invoke.assert_called_once_with(
                {
                    "topic": "职场",
                    "style": "自嘲",
                    "duration": 5,
                    "audience": "互联网人",
                    "debug": False,
                }
            )

    def test_ingest(self, capsys):
        """ingest 子命令导入知识库。"""
        with patch(
            "comedy_agent.api.cli.KnowledgeIngestor"
        ) as mock_cls:
            mock_ingestor = MagicMock()
            mock_ingestor.ingest_directory.return_value = {
                "raw_docs": 3,
                "chunks": 5,
                "ingested": 5,
                "collection": "comedy_knowledge",
            }
            mock_cls.return_value = mock_ingestor

            code = main(["ingest", "--dir", "data/knowledge"])

            assert code == 0
            captured = capsys.readouterr()
            assert "导入完成" in captured.out
            assert "3" in captured.out
            assert "5" in captured.out
            mock_ingestor.ingest_directory.assert_called_once_with("data/knowledge")

    def test_feedback_loop(self, capsys):
        """feedback-loop 子命令触发回流。"""
        with patch("comedy_agent.api.cli._get_memory") as mock_get_memory:
            mock_memory = MagicMock()
            mock_get_memory.return_value = mock_memory

            with patch(
                "comedy_agent.api.cli.FeedbackLoop"
            ) as mock_loop_cls:
                mock_loop = MagicMock()
                mock_loop.ingest_high_rated_scripts.return_value = {
                    "ingested_scripts": 2,
                    "total_chunks": 5,
                    "script_ids": ["s1", "s2"],
                    "skipped": [],
                    "dry_run": False,
                }
                mock_loop_cls.return_value = mock_loop

                code = main([
                    "feedback-loop",
                    "--user-id", "u001",
                    "--min-rating", "4.0",
                    "--strategy", "paragraph",
                ])

                assert code == 0
                captured = capsys.readouterr()
                assert "实际回流: 2 条作品" in captured.out
                mock_loop_cls.assert_called_once_with(
                    memory=mock_memory, min_rating=4.0
                )
                mock_loop.ingest_high_rated_scripts.assert_called_once_with(
                    user_id="u001",
                    chunk_strategy="paragraph",
                    dry_run=False,
                )

    def test_feedback_loop_dry_run(self, capsys):
        """feedback-loop --dry-run 模拟运行。"""
        with patch("comedy_agent.api.cli._get_memory") as mock_get_memory:
            mock_memory = MagicMock()
            mock_get_memory.return_value = mock_memory

            with patch(
                "comedy_agent.api.cli.FeedbackLoop"
            ) as mock_loop_cls:
                mock_loop = MagicMock()
                mock_loop.ingest_high_rated_scripts.return_value = {
                    "ingested_scripts": 0,
                    "total_chunks": 0,
                    "script_ids": [],
                    "skipped": [],
                    "dry_run": True,
                }
                mock_loop_cls.return_value = mock_loop

                code = main(["feedback-loop", "--dry-run"])
                assert code == 0
                captured = capsys.readouterr()
                assert "[模拟运行]" in captured.out
