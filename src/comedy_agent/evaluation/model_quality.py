"""模型输出质量评估 —— 格式合规、重复率、结构完整性等启发式指标。

同样不依赖外部 LLM 调用，支持快速回归测试。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelOutputResult:
    """模型输出质量评估结果。"""

    format_compliance: float = 0.0
    repetition_score: float = 0.0
    structure_score: float = 0.0
    length_score: float = 0.0
    has_punchline: bool = False
    has_dialogue: bool = False

    overall_score: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "format_compliance": self.format_compliance,
            "repetition_score": self.repetition_score,
            "structure_score": self.structure_score,
            "length_score": self.length_score,
            "has_punchline": self.has_punchline,
            "has_dialogue": self.has_dialogue,
            "details": self.details,
            "suggestions": self.suggestions,
        }


class ModelOutputEvaluator:
    """模型输出质量评估器。

    评估 LLM 生成内容的质量，包括格式合规、重复率、结构完整性等。
    """

    DEFAULT_WEIGHTS: dict[str, float] = {
        "format_compliance": 0.20,
        "repetition_score": 0.20,
        "structure_score": 0.20,
        "length_score": 0.15,
        "has_punchline": 0.15,
        "has_dialogue": 0.10,
    }

    # 常见输出格式标记
    FORMAT_MARKERS = {
        "markdown_headers": re.compile(r"^#{1,6}\s+", re.MULTILINE),
        "numbered_list": re.compile(r"^\d+[.、)）]\s+", re.MULTILINE),
        "bullet_list": re.compile(r"^[-*•]\s+", re.MULTILINE),
        "code_block": re.compile(r"```"),
        "dialogue_colon": re.compile(r"[\u4e00-\u9fa5A-Za-z0-9_]+[：:]\s*"),
        "quotation": re.compile(r'[\u201c\u201d"\u2018\u2019\']'),
    }

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}

    def evaluate(
        self,
        output: str,
        expected_format: str | None = None,
        min_length: int = 100,
        max_length: int = 5000,
    ) -> ModelOutputResult:
        """评估模型输出质量。

        Args:
            output: 模型生成的文本。
            expected_format: 期望的输出格式，如 "markdown" / "json" / "dialogue" / None。
            min_length: 最小期望长度。
            max_length: 最大期望长度。

        Returns:
            ModelOutputResult: 评估结果。
        """
        if not output or not output.strip():
            return ModelOutputResult(
                overall_score=0.0,
                suggestions=["输出为空。"],
            )

        text = output.strip()

        fc = self._score_format(text, expected_format)
        rs = self._score_repetition(text)
        ss = self._score_structure(text)
        ls = self._score_length(text, min_length, max_length)
        hp = self._has_punchline(text)
        hd = self._has_dialogue(text)

        overall = (
            fc * self.weights["format_compliance"]
            + rs * self.weights["repetition_score"]
            + ss * self.weights["structure_score"]
            + ls * self.weights["length_score"]
            + (10.0 if hp else 0.0) * self.weights["has_punchline"]
            + (10.0 if hd else 0.0) * self.weights["has_dialogue"]
        )
        overall = round(min(10.0, max(0.0, overall)), 2)

        suggestions = self._generate_suggestions(
            format_compliance=fc,
            repetition_score=rs,
            structure_score=ss,
            length_score=ls,
            has_punchline=hp,
            has_dialogue=hd,
        )

        return ModelOutputResult(
            format_compliance=round(fc, 2),
            repetition_score=round(rs, 2),
            structure_score=round(ss, 2),
            length_score=round(ls, 2),
            has_punchline=hp,
            has_dialogue=hd,
            overall_score=overall,
            details={
                "char_count": len(text),
                "line_count": len(text.splitlines()),
                "paragraph_count": len([p for p in text.split("\n\n") if p.strip()]),
            },
            suggestions=suggestions,
        )

    # ------------------------------------------------------------------ #
    # 内部评分
    # ------------------------------------------------------------------ #
    def _score_format(self, text: str, expected: str | None) -> float:
        """格式合规评分（0-10）。"""
        if expected is None:
            # 无特定格式要求，只要有基本结构即可
            markers_found = sum(
                1 for pat in self.FORMAT_MARKERS.values() if pat.search(text)
            )
            return min(10.0, markers_found / 2 * 10)

        expected = expected.lower()
        score = 0.0

        if expected == "markdown":
            if self.FORMAT_MARKERS["markdown_headers"].search(text):
                score += 4.0
            if self.FORMAT_MARKERS["bullet_list"].search(text):
                score += 3.0
            if self.FORMAT_MARKERS["numbered_list"].search(text):
                score += 3.0

        elif expected == "json":
            text_clean = text.strip()
            if text_clean.startswith(("{", "[")) and text_clean.endswith(("}", "]")):
                score = 10.0
            elif "{" in text and "}" in text:
                score = 5.0

        elif expected == "dialogue":
            if self.FORMAT_MARKERS["dialogue_colon"].search(text):
                score += 5.0
            if self.FORMAT_MARKERS["quotation"].search(text):
                score += 5.0

        else:
            score = 5.0  # 未知格式给中性分

        return score

    @staticmethod
    def _score_repetition(text: str) -> float:
        """重复率评分（0-10，越高表示重复越少）。"""
        sentences = [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]
        if len(sentences) < 3:
            return 5.0

        # 检测连续重复的句子（模糊匹配）
        repeats = 0
        for i in range(1, len(sentences)):
            if sentences[i] == sentences[i - 1]:
                repeats += 1
            # 检测子串重复（超过 80% 相似）
            elif len(sentences[i]) > 10 and len(sentences[i - 1]) > 10:
                shorter = min(sentences[i], sentences[i - 1], key=len)
                longer = max(sentences[i], sentences[i - 1], key=len)
                if shorter in longer or len(set(shorter) & set(longer)) / len(set(longer)) > 0.8:
                    repeats += 0.5

        repeat_ratio = repeats / len(sentences)
        return max(0.0, 10 - repeat_ratio * 50)

    @staticmethod
    def _score_structure(text: str) -> float:
        """结构完整性评分（0-10）。"""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) >= 4:
            return 10.0
        elif len(paragraphs) >= 2:
            return 5.0 + (len(paragraphs) - 2) * 2.5
        else:
            return 2.5

    @staticmethod
    def _score_length(text: str, min_len: int, max_len: int) -> float:
        """长度适中性评分（0-10）。"""
        length = len(text)
        if min_len <= length <= max_len:
            return 10.0
        elif length < min_len:
            return max(0.0, length / min_len * 10)
        else:
            return max(0.0, 10 - (length - max_len) / max_len * 5)

    @staticmethod
    def _has_punchline(text: str) -> bool:
        """是否包含笑点信号。"""
        punchline_words = {"笑", "哈哈", "包袱", "反转", "转折", "意外", "没想到", "funny", "joke", "punchline"}
        return any(w in text for w in punchline_words)

    @staticmethod
    def _has_dialogue(text: str) -> bool:
        """是否包含对话。"""
        return ":" in text or "：" in text or "\"" in text or "\"" in text

    @staticmethod
    def _generate_suggestions(**scores: Any) -> list[str]:
        """生成改进建议。"""
        suggestions: list[str] = []
        if scores.get("format_compliance", 10) < 5:
            suggestions.append("格式不够规范，建议增加标题、列表或分段。")
        if scores.get("repetition_score", 10) < 5:
            suggestions.append("存在明显重复内容，建议删减或改写重复句子。")
        if scores.get("structure_score", 10) < 5:
            suggestions.append("结构较松散，建议增加段落划分，明确内容层次。")
        if scores.get("length_score", 10) < 5:
            suggestions.append("输出长度不合适，建议调整篇幅。")
        if not scores.get("has_punchline", True):
            suggestions.append("未检测到笑点信号，建议增加包袱或反转元素。")
        if not scores.get("has_dialogue", True):
            suggestions.append("未检测到对话格式，建议增加角色对白。")
        if not suggestions:
            suggestions.append("输出质量良好。")
        return suggestions
