"""评估体系核心模块测试 —— 剧本质量、检索质量、模型输出、回归套件。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from langchain_core.documents import Document

from comedy_agent.evaluation.script_quality import ScriptQualityEvaluator, ScriptQualityResult
from comedy_agent.evaluation.retrieval_quality import RetrievalEvaluator, RetrievalResult
from comedy_agent.evaluation.model_quality import ModelOutputEvaluator, ModelOutputResult
from comedy_agent.evaluation.regression import EvaluationSuite, TestCase, run_suite
from comedy_agent.evaluation.report import EvaluationReport


# ------------------------------------------------------------------ #
# ScriptQualityEvaluator
# ------------------------------------------------------------------ #
class TestScriptQualityEvaluator:
    def test_empty_script(self):
        evaluator = ScriptQualityEvaluator()
        result = evaluator.evaluate("")
        assert result.overall_score == 0.0
        assert "为空" in result.suggestions[0]

    def test_minimal_script(self):
        evaluator = ScriptQualityEvaluator()
        script = "大家好，今天我想聊聊工作。\n\n甲：你最近忙吗？\n乙：忙啊，天天加班。\n\n最后，谢谢大家！"
        result = evaluator.evaluate(script, script_type="standup")
        assert result.overall_score > 0
        assert result.structure_completeness > 0
        assert result.dialogue_ratio > 0
        assert 0 <= result.overall_score <= 10

    def test_script_with_punchlines(self):
        evaluator = ScriptQualityEvaluator()
        script = (
            "开场：大家好！\n\n"
            "甲：你知道什么叫加班吗？\n"
            "乙：不知道。\n"
            "甲：就是老板觉得你的时间不值钱。哈哈！\n\n"
            "反转：没想到吧，我其实是个程序员。\n\n"
            "结尾：谢谢大家！"
        )
        result = evaluator.evaluate(script)
        assert result.punchline_density > 0
        assert result.details["punchline_hits"] >= 2  # 至少 "哈哈" 和 "反转"

    def test_custom_weights(self):
        weights = {"punchline_density": 1.0}  # 只看重笑点密度
        evaluator = ScriptQualityEvaluator(weights=weights)
        script = "哈哈！" * 30  # 确保长度超过 50
        result = evaluator.evaluate(script)
        # 即使其他维度为0，笑点密度高也能拉高总分
        assert result.punchline_density > 0

    def test_length_expectations(self):
        evaluator = ScriptQualityEvaluator()
        short = "大家好，谢谢。"
        result = evaluator.evaluate(short, script_type="standup")
        # 脱口秀期望 800-3000 字，短文本长度分应该低
        assert result.length_score < 10

    def test_result_to_dict(self):
        result = ScriptQualityResult(overall_score=7.5, punchline_density=8.0)
        d = result.to_dict()
        assert d["overall_score"] == 7.5
        assert d["punchline_density"] == 8.0
        assert "suggestions" in d


# ------------------------------------------------------------------ #
# RetrievalEvaluator
# ------------------------------------------------------------------ #
class TestRetrievalEvaluator:
    def test_recall_at_k(self):
        evaluator = RetrievalEvaluator(k_values=(1, 3))
        docs = [
            Document(page_content="a", metadata={"doc_id": "d1"}),
            Document(page_content="b", metadata={"doc_id": "d2"}),
            Document(page_content="c", metadata={"doc_id": "d3"}),
        ]
        result = evaluator.evaluate(
            query="test",
            retrieved=docs,
            relevant_doc_ids={"d1", "d3"},
        )
        assert result.recall_at_k[1] == 0.5  # d1 在 top1，recall=1/2
        assert result.recall_at_k[3] == 1.0  # d1,d3 都在 top3
        assert result.precision_at_k[1] == 1.0  # top1 全相关
        assert result.mrr == 1.0  # 第一个相关在位置1

    def test_mrr_second_position(self):
        evaluator = RetrievalEvaluator(k_values=(1, 3))
        docs = [
            Document(page_content="a", metadata={"doc_id": "d2"}),
            Document(page_content="b", metadata={"doc_id": "d1"}),
        ]
        result = evaluator.evaluate(
            query="test",
            retrieved=docs,
            relevant_doc_ids={"d1"},
        )
        assert result.mrr == 0.5  # 第一个相关在位置2

    def test_no_relevant(self):
        evaluator = RetrievalEvaluator(k_values=(1,))
        docs = [Document(page_content="a", metadata={"doc_id": "d1"})]
        result = evaluator.evaluate(
            query="test",
            retrieved=docs,
            relevant_doc_ids=set(),
        )
        assert result.recall_at_k[1] == 0.0
        assert result.mrr == 0.0

    def test_batch_evaluate(self):
        evaluator = RetrievalEvaluator(k_values=(1, 3))
        docs1 = [
            Document(page_content="a", metadata={"doc_id": "d1"}),
            Document(page_content="b", metadata={"doc_id": "d2"}),
        ]
        docs2 = [
            Document(page_content="c", metadata={"doc_id": "d3"}),
        ]
        batch = evaluator.evaluate_batch(
            queries=["q1", "q2"],
            all_retrieved=[docs1, docs2],
            all_relevant=[{"d1"}, {"d3"}],
        )
        assert batch.avg_recall_at_k[1] == 1.0
        assert batch.avg_mrr == 1.0
        assert len(batch.per_query) == 2

    def test_ndcg(self):
        evaluator = RetrievalEvaluator(k_values=(3,))
        docs = [
            Document(page_content="a", metadata={"doc_id": "d1"}),
            Document(page_content="b", metadata={"doc_id": "d2"}),
            Document(page_content="c", metadata={"doc_id": "d3"}),
        ]
        result = evaluator.evaluate(
            query="test",
            retrieved=docs,
            relevant_doc_ids={"d1", "d3"},
            relevance_scores={"d1": 1.0, "d3": 0.5},
        )
        assert 0 <= result.ndcg_at_k[3] <= 1.0


# ------------------------------------------------------------------ #
# ModelOutputEvaluator
# ------------------------------------------------------------------ #
class TestModelOutputEvaluator:
    def test_empty_output(self):
        evaluator = ModelOutputEvaluator()
        result = evaluator.evaluate("")
        assert result.overall_score == 0.0

    def test_good_markdown_output(self):
        evaluator = ModelOutputEvaluator()
        output = "# 标题\n\n- 第一点\n- 第二点\n\n1. 编号一\n2. 编号二\n"
        result = evaluator.evaluate(output, expected_format="markdown")
        assert result.format_compliance > 5
        assert result.structure_score > 5

    def test_repetition_detection(self):
        evaluator = ModelOutputEvaluator()
        output = "这是一句话。这是一句话。这是一句话。"
        result = evaluator.evaluate(output)
        assert result.repetition_score < 5

    def test_has_punchline_and_dialogue(self):
        evaluator = ModelOutputEvaluator()
        output = '甲：你知道吗？哈哈！\n乙：不知道。\n甲：反转来了！'
        result = evaluator.evaluate(output)
        assert result.has_punchline is True
        assert result.has_dialogue is True

    def test_result_to_dict(self):
        result = ModelOutputResult(overall_score=8.0, has_punchline=True)
        d = result.to_dict()
        assert d["overall_score"] == 8.0
        assert d["has_punchline"] is True


# ------------------------------------------------------------------ #
# Regression / Suite
# ------------------------------------------------------------------ #
class TestEvaluationSuite:
    def test_from_json(self, tmp_path: Path):
        data = {
            "name": "test-suite",
            "cases": [
                {
                    "name": "script-1",
                    "type": "script_quality",
                    "input": {"script": "大家好！\n\n甲：你好。\n\n谢谢大家！", "script_type": "standup"},
                    "expected": {"min_score": 3.0},
                }
            ],
        }
        path = tmp_path / "suite.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        suite = EvaluationSuite.from_json(path)
        assert suite.name == "test-suite"
        assert len(suite.cases) == 1
        assert suite.cases[0].name == "script-1"

    def test_to_dict(self):
        suite = EvaluationSuite(name="suite", cases=[
            TestCase(name="c1", type="script_quality", input_data={"script": "x"})
        ])
        d = suite.to_dict()
        assert d["name"] == "suite"

    def test_run_suite(self, tmp_path: Path):
        data = {
            "name": "integration-suite",
            "cases": [
                {
                    "name": "good-script",
                    "type": "script_quality",
                    "input": {
                        "script": "开场：大家好！\n\n甲：你好。\n乙：你好。\n\n反转：没想到吧！\n\n结尾：谢谢！",
                        "script_type": "default",
                    },
                    "expected": {"min_score": 1.0},
                },
                {
                    "name": "good-output",
                    "type": "model_output",
                    "input": {
                        "output": "# 报告\n\n- 笑点分析\n- 结构建议\n",
                        "expected_format": "markdown",
                    },
                    "expected": {"min_score": 1.0},
                },
            ],
        }
        path = tmp_path / "suite.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        suite = EvaluationSuite.from_json(path)
        report = run_suite(suite)
        assert report.pass_rate == 1.0
        assert report.avg_score > 0
        assert report.total_duration_ms >= 0
        assert len(report.results) == 2


# ------------------------------------------------------------------ #
# EvaluationReport
# ------------------------------------------------------------------ #
class TestEvaluationReport:
    def test_summary_empty(self):
        report = EvaluationReport(suite_name="empty")
        assert report.pass_rate == 0.0
        assert report.avg_score == 0.0
        assert report.summary()["total_cases"] == 0

    def test_summary_with_results(self):
        report = EvaluationReport(suite_name="test")
        report.add_result("case1", "script_quality", 8.0, {"score": 8.0}, passed=True)
        report.add_result("case2", "script_quality", 4.0, {"score": 4.0}, passed=False)
        summary = report.summary()
        assert summary["total_cases"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["pass_rate"] == 0.5
        assert summary["avg_score"] == 6.0

    def test_to_markdown(self):
        report = EvaluationReport(suite_name="md-test")
        report.add_result("c1", "t", 9.0, {}, passed=True)
        md = report.to_markdown()
        assert "# 评估报告: md-test" in md
        assert "c1" in md
        assert "通过" in md or "✅" in md

    def test_to_json(self):
        report = EvaluationReport(suite_name="json-test")
        report.add_result("c1", "t", 7.5, {}, passed=True)
        j = report.to_json()
        assert '"suite_name": "json-test"' in j
        assert "7.5" in j
