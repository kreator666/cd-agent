"""评估体系 —— 剧本质量、检索相关性、模型输出的自动化评估。

提供基于规则/启发式的快速评估指标，以及回归测试框架，
支持定期运行、生成报告与基准对比。
"""

from __future__ import annotations

from comedy_agent.evaluation.script_quality import ScriptQualityEvaluator
from comedy_agent.evaluation.retrieval_quality import RetrievalEvaluator
from comedy_agent.evaluation.model_quality import ModelOutputEvaluator
from comedy_agent.evaluation.regression import EvaluationSuite, run_suite
from comedy_agent.evaluation.report import EvaluationReport

__all__ = [
    "ScriptQualityEvaluator",
    "RetrievalEvaluator",
    "ModelOutputEvaluator",
    "EvaluationSuite",
    "run_suite",
    "EvaluationReport",
]
