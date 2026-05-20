"""评估报告 —— 结构化报告生成与导出。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResultEntry:
    """单条评估结果条目。"""

    case_name: str
    case_type: str
    score: float
    passed: bool
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_name": self.case_name,
            "case_type": self.case_type,
            "score": self.score,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "data": self.data,
        }


@dataclass
class EvaluationReport:
    """评估报告。"""

    suite_name: str = ""
    results: list[ResultEntry] = field(default_factory=list)
    total_duration_ms: float = 0.0
    _durations: dict[str, float] = field(default_factory=dict, repr=False)

    def add_result(
        self,
        case_name: str,
        case_type: str,
        score: float,
        data: dict[str, Any],
        passed: bool = True,
    ) -> None:
        """添加一条评估结果。"""
        self.results.append(
            ResultEntry(
                case_name=case_name,
                case_type=case_type,
                score=score,
                passed=passed,
                data=data,
                duration_ms=round(self._durations.get(case_name, 0.0) * 1000, 2),
            )
        )

    def record_duration(self, case_name: str, seconds: float) -> None:
        """记录单条用例执行耗时。"""
        self._durations[case_name] = seconds

    @property
    def pass_rate(self) -> float:
        """通过率。"""
        if not self.results:
            return 0.0
        passed = sum(1 for r in self.results if r.passed)
        return round(passed / len(self.results), 4)

    @property
    def avg_score(self) -> float:
        """平均得分。"""
        if not self.results:
            return 0.0
        return round(sum(r.score for r in self.results) / len(self.results), 2)

    def summary(self) -> dict[str, Any]:
        """生成摘要。"""
        by_type: dict[str, list[float]] = {}
        for r in self.results:
            by_type.setdefault(r.case_type, []).append(r.score)

        type_avg = {
            t: round(sum(scores) / len(scores), 2)
            for t, scores in by_type.items()
        }

        return {
            "suite_name": self.suite_name,
            "total_cases": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "pass_rate": self.pass_rate,
            "avg_score": self.avg_score,
            "total_duration_ms": self.total_duration_ms,
            "by_type": type_avg,
        }

    def to_dict(self) -> dict[str, Any]:
        """导出为字典。"""
        return {
            **self.summary(),
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        """导出为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_markdown(self) -> str:
        """导出为 Markdown 报告。"""
        lines: list[str] = [
            f"# 评估报告: {self.suite_name}",
            "",
            "## 摘要",
            "",
            f"- **总用例数**: {len(self.results)}",
            f"- **通过**: {sum(1 for r in self.results if r.passed)}",
            f"- **失败**: {sum(1 for r in self.results if not r.passed)}",
            f"- **通过率**: {self.pass_rate * 100:.1f}%",
            f"- **平均得分**: {self.avg_score}",
            f"- **总耗时**: {self.total_duration_ms:.0f}ms",
            "",
            "## 详细结果",
            "",
            "| 用例 | 类型 | 得分 | 状态 | 耗时(ms) |",
            "|------|------|------|------|----------|",
        ]

        for r in self.results:
            status = "✅ 通过" if r.passed else "❌ 失败"
            lines.append(
                f"| {r.case_name} | {r.case_type} | {r.score} | {status} | {r.duration_ms} |"
            )

        lines.append("")
        return "\n".join(lines)
