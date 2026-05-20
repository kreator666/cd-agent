"""回归测试框架 —— 评估套件定义、批量执行与基准对比。

支持从 JSON/YAML 加载测试用例，运行评估流水线，生成结构化报告。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from comedy_agent.evaluation.script_quality import ScriptQualityEvaluator
from comedy_agent.evaluation.retrieval_quality import RetrievalEvaluator
from comedy_agent.evaluation.model_quality import ModelOutputEvaluator
from comedy_agent.evaluation.report import EvaluationReport


@dataclass
class TestCase:
    """单条测试用例。"""

    name: str
    type: str  # "script_quality" | "retrieval" | "model_output"
    input_data: dict[str, Any]
    expected: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestCase":
        return cls(
            name=data["name"],
            type=data["type"],
            input_data=data["input"],
            expected=data.get("expected"),
        )


@dataclass
class EvaluationSuite:
    """评估测试套件。"""

    name: str
    cases: list[TestCase] = field(default_factory=list)

    @classmethod
    def from_json(cls, path: str | Path) -> "EvaluationSuite":
        """从 JSON 文件加载测试套件。"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            name=data.get("name", "unnamed"),
            cases=[TestCase.from_dict(c) for c in data.get("cases", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cases": [
                {
                    "name": c.name,
                    "type": c.type,
                    "input": c.input_data,
                    "expected": c.expected,
                }
                for c in self.cases
            ],
        }


def run_suite(
    suite: EvaluationSuite,
    script_evaluator: ScriptQualityEvaluator | None = None,
    retrieval_evaluator: RetrievalEvaluator | None = None,
    model_evaluator: ModelOutputEvaluator | None = None,
) -> EvaluationReport:
    """运行评估套件并生成报告。

    Args:
        suite: 评估测试套件。
        script_evaluator: 剧本质量评估器（可选，默认新建）。
        retrieval_evaluator: 检索质量评估器（可选，默认新建）。
        model_evaluator: 模型输出评估器（可选，默认新建）。

    Returns:
        EvaluationReport: 结构化评估报告。
    """
    script_evaluator = script_evaluator or ScriptQualityEvaluator()
    retrieval_evaluator = retrieval_evaluator or RetrievalEvaluator()
    model_evaluator = model_evaluator or ModelOutputEvaluator()

    report = EvaluationReport(suite_name=suite.name)
    start_time = time.time()

    for case in suite.cases:
        case_start = time.time()
        try:
            if case.type == "script_quality":
                result = script_evaluator.evaluate(
                    script=case.input_data["script"],
                    script_type=case.input_data.get("script_type", "default"),
                )
                report.add_result(
                    case_name=case.name,
                    case_type=case.type,
                    score=result.overall_score,
                    data=result.to_dict(),
                    passed=_check_threshold(result.overall_score, case.expected, "overall_score"),
                )

            elif case.type == "model_output":
                result = model_evaluator.evaluate(
                    output=case.input_data["output"],
                    expected_format=case.input_data.get("expected_format"),
                    min_length=case.input_data.get("min_length", 100),
                    max_length=case.input_data.get("max_length", 5000),
                )
                report.add_result(
                    case_name=case.name,
                    case_type=case.type,
                    score=result.overall_score,
                    data=result.to_dict(),
                    passed=_check_threshold(result.overall_score, case.expected, "overall_score"),
                )

            elif case.type == "retrieval":
                from langchain_core.documents import Document

                docs = [
                    Document(
                        page_content=d["content"],
                        metadata=d.get("metadata", {}),
                    )
                    for d in case.input_data["retrieved"]
                ]
                relevant = set(case.input_data["relevant_doc_ids"])
                rel_scores = case.input_data.get("relevance_scores")
                result = retrieval_evaluator.evaluate(
                    query=case.input_data["query"],
                    retrieved=docs,
                    relevant_doc_ids=relevant,
                    relevance_scores=rel_scores,
                )
                # 检索用 mrr 作为主分
                score = result.mrr * 10
                report.add_result(
                    case_name=case.name,
                    case_type=case.type,
                    score=round(score, 2),
                    data=result.to_dict(),
                    passed=_check_threshold(score, case.expected, "mrr"),
                )

            else:
                report.add_result(
                    case_name=case.name,
                    case_type=case.type,
                    score=0.0,
                    data={"error": f"未知测试类型: {case.type}"},
                    passed=False,
                )

        except Exception as e:
            report.add_result(
                case_name=case.name,
                case_type=case.type,
                score=0.0,
                data={"error": str(e)},
                passed=False,
            )

        report.record_duration(case.name, time.time() - case_start)

    report.total_duration_ms = round((time.time() - start_time) * 1000, 2)
    return report


def _check_threshold(
    actual: float,
    expected: dict[str, Any] | None,
    key: str,
) -> bool:
    """检查实际值是否满足预期阈值。"""
    if expected is None:
        return True
    threshold = expected.get("min_score") or expected.get(key)
    if threshold is not None:
        return actual >= float(threshold)
    return True
