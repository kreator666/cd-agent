"""剧本质量评估 —— 基于规则与启发式的快速喜剧剧本质量指标。

不依赖 LLM 调用，适合在 CI/CD 流水线中快速回归测试。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ------------------------------------------------------------------ #
# 喜剧专用规则库
# ------------------------------------------------------------------ #

# 笑点相关关键词（中文 + 英文常见表达）
_PUNCHLINE_KEYWORDS = {
    "笑", "哈哈", "呵呵", "嘿嘿", "噗", "噗嗤", "噗哈哈",
    "笑点", "包袱", "抖", "反转", "转折", "意外", "没想到",
    "居然", "竟然", "原来", "才发现", "才明白",
    "funny", "laugh", "joke", "punchline", "twist",
}

# 口语化词汇（越高越适合舞台）
_COLLOQUIAL_WORDS = {
    "咱", "咱们", "你", "我", "他", "她", "这", "那",
    "咋", "啥", "呗", "嘛", "呢", "啊", "呀", "吧",
    "得了", "得了吧", "可不是", "就是说", "话说回来",
    "怎么说呢", "说白了", "说白了就", "说白了也是",
    "哎", "哎呀", "哎哟", "嗨", "哟", "嘿",
}

# 结构关键词
_STRUCTURE_KEYWORDS = {
    "起": {"开头", "开场", "引入", "铺垫", "从前", "有一天", "话说"},
    "承": {"接着", "然后", "后来", "之后", "接下来", "随之", "于是"},
    "转": {"但是", "然而", "可是", "不过", "没想到", "谁知", "突然", "反转", "转折"},
    "合": {"最后", "结尾", "结局", "总之", "说到底", "归根结底", "收场", "落幕"},
}

_RE_SENTENCE = re.compile(r"[。！？\n;；!?.]+")
_RE_PUNCTUATION = re.compile(r"[。！？，、；：\"\"'']")


@dataclass
class ScriptQualityResult:
    """剧本质量评估结果。"""

    punchline_density: float = 0.0
    dialogue_ratio: float = 0.0
    structure_completeness: float = 0.0
    word_diversity: float = 0.0
    colloquial_score: float = 0.0
    length_score: float = 0.0
    readability: float = 0.0

    # 综合评分
    overall_score: float = 0.0
    # 各维度详细数据
    details: dict[str, Any] = field(default_factory=dict)
    # 改进建议
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "punchline_density": self.punchline_density,
            "dialogue_ratio": self.dialogue_ratio,
            "structure_completeness": self.structure_completeness,
            "word_diversity": self.word_diversity,
            "colloquial_score": self.colloquial_score,
            "length_score": self.length_score,
            "readability": self.readability,
            "details": self.details,
            "suggestions": self.suggestions,
        }


class ScriptQualityEvaluator:
    """剧本质量评估器。

    基于规则和启发式快速计算多项喜剧剧本质量指标，
    无需调用外部 LLM，适合回归测试和流水线中使用。
    """

    # 各维度权重（可覆盖）
    DEFAULT_WEIGHTS: dict[str, float] = {
        "punchline_density": 0.20,
        "dialogue_ratio": 0.15,
        "structure_completeness": 0.20,
        "word_diversity": 0.10,
        "colloquial_score": 0.15,
        "length_score": 0.10,
        "readability": 0.10,
    }

    # 长度期望（按剧本类型，单位：字符数）
    LENGTH_EXPECTATIONS: dict[str, tuple[int, int]] = {
        "standup": (800, 3000),
        "crosstalk": (1500, 5000),
        "sketch": (2000, 6000),
        "sitcom": (3000, 10000),
        "joke": (100, 500),
        "default": (500, 5000),
    }

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}

    # ------------------------------------------------------------------ #
    # 公共 API
    # ------------------------------------------------------------------ #
    def evaluate(
        self,
        script: str,
        script_type: str = "default",
    ) -> ScriptQualityResult:
        """评估单部剧本质量。

        Args:
            script: 剧本文本内容。
            script_type: 剧本类型，影响长度期望。可选：
                standup / crosstalk / sketch / sitcom / joke / default。

        Returns:
            ScriptQualityResult: 包含各维度评分与改进建议的结果。
        """
        if not script or not script.strip():
            return ScriptQualityResult(
                overall_score=0.0,
                suggestions=["剧本内容为空，无法评估。"],
            )

        text = script.strip()

        # 各维度评分（0-10 分制）
        pd = self._score_punchline_density(text)
        dr = self._score_dialogue_ratio(text)
        sc = self._score_structure(text)
        wd = self._score_word_diversity(text)
        cs = self._score_colloquial(text)
        ls = self._score_length(text, script_type)
        rb = self._score_readability(text)

        # 加权综合
        overall = (
            pd * self.weights["punchline_density"]
            + dr * self.weights["dialogue_ratio"]
            + sc * self.weights["structure_completeness"]
            + wd * self.weights["word_diversity"]
            + cs * self.weights["colloquial_score"]
            + ls * self.weights["length_score"]
            + rb * self.weights["readability"]
        )
        overall = round(min(10.0, max(0.0, overall)), 2)

        # 生成建议
        suggestions = self._generate_suggestions(
            punchline_density=pd,
            dialogue_ratio=dr,
            structure_completeness=sc,
            word_diversity=wd,
            colloquial_score=cs,
            length_score=ls,
            readability=rb,
        )

        return ScriptQualityResult(
            punchline_density=round(pd, 2),
            dialogue_ratio=round(dr, 2),
            structure_completeness=round(sc, 2),
            word_diversity=round(wd, 2),
            colloquial_score=round(cs, 2),
            length_score=round(ls, 2),
            readability=round(rb, 2),
            overall_score=overall,
            details={
                "char_count": len(text),
                "sentence_count": len(_RE_SENTENCE.split(text)),
                "punchline_hits": len(
                    [w for w in _PUNCHLINE_KEYWORDS if w in text]
                ),
            },
            suggestions=suggestions,
        )

    # ------------------------------------------------------------------ #
    # 内部评分方法
    # ------------------------------------------------------------------ #
    @staticmethod
    def _score_punchline_density(text: str) -> float:
        """笑点密度评分（0-10）。"""
        if len(text) < 50:
            return 0.0

        hits = sum(1 for kw in _PUNCHLINE_KEYWORDS if kw in text)
        exclamation = text.count("！") + text.count("!")
        question = text.count("？") + text.count("?")

        # 每 500 字期望至少 2 个笑点信号
        score = (hits + exclamation * 0.3 + question * 0.2) / (len(text) / 500) * 2
        return min(10.0, score)

    @staticmethod
    def _score_dialogue_ratio(text: str) -> float:
        """对话占比评分（0-10）。"""
        total = len(text)
        if total == 0:
            return 0.0

        # 检测冒号引导的对话行
        dialogue_lines = [ln for ln in text.split("\n") if ":" in ln or "：" in ln]
        dialogue_chars = sum(len(ln) for ln in dialogue_lines)

        # 也检测引号包裹的内容（简单匹配）
        quoted_chars = 0
        for quote_pair in (("\"", "\""), ("'", "'"), ("\u201c", "\u201d"), ("\u2018", "\u2019")):
            start, end = quote_pair
            idx = 0
            while True:
                s = text.find(start, idx)
                if s == -1:
                    break
                e = text.find(end, s + 1)
                if e == -1:
                    break
                quoted_chars += e - s + 1
                idx = e + 1

        ratio = (dialogue_chars + quoted_chars) / total
        # 对话占比 40%-70% 为最佳
        if 0.4 <= ratio <= 0.7:
            return 10.0
        elif ratio < 0.4:
            return ratio / 0.4 * 10
        else:
            return max(0.0, 10 - (ratio - 0.7) / 0.3 * 10)

    @staticmethod
    def _score_structure(text: str) -> float:
        """结构完整性评分（0-10）。"""
        scores = []
        for phase, keywords in _STRUCTURE_KEYWORDS.items():
            hit = any(kw in text for kw in keywords)
            scores.append(1.0 if hit else 0.0)

        # 起承转合四个阶段
        phase_score = sum(scores) / len(scores) * 10

        # 段落数量加分（至少 3 段以上）
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        para_bonus = min(2.0, len(paragraphs) / 3)

        return min(10.0, phase_score + para_bonus)

    @staticmethod
    def _score_word_diversity(text: str) -> float:
        """词汇多样性评分（0-10）。"""
        # 提取中文字符和英文单词
        zh_chars = re.findall(r"[\u4e00-\u9fa5]", text)
        en_words = re.findall(r"[a-zA-Z]+", text)

        all_tokens = zh_chars + [w.lower() for w in en_words]
        if not all_tokens:
            return 0.0

        unique = len(set(all_tokens))
        total = len(all_tokens)
        ratio = unique / total

        # 多样性 0.5-0.8 为最佳
        if 0.5 <= ratio <= 0.8:
            return 10.0
        elif ratio < 0.5:
            return ratio / 0.5 * 10
        else:
            return max(0.0, 10 - (ratio - 0.8) / 0.2 * 10)

    @staticmethod
    def _score_colloquial(text: str) -> float:
        """口语化程度评分（0-10）。"""
        if len(text) < 50:
            return 5.0

        hits = sum(1 for w in _COLLOQUIAL_WORDS if w in text)
        # 每 500 字期望 3-8 个口语词
        density = hits / (len(text) / 500)
        if 3 <= density <= 8:
            return 10.0
        elif density < 3:
            return density / 3 * 10
        else:
            return max(0.0, 10 - (density - 8) / 4 * 10)

    def _score_length(self, text: str, script_type: str) -> float:
        """长度适中性评分（0-10）。"""
        expected = self.LENGTH_EXPECTATIONS.get(script_type, self.LENGTH_EXPECTATIONS["default"])
        min_len, max_len = expected
        length = len(text)

        if min_len <= length <= max_len:
            return 10.0
        elif length < min_len:
            return max(0.0, length / min_len * 10)
        else:
            return max(0.0, 10 - (length - max_len) / max_len * 5)

    @staticmethod
    def _score_readability(text: str) -> float:
        """可读性评分（0-10）。"""
        sentences = [s.strip() for s in _RE_SENTENCE.split(text) if s.strip()]
        if not sentences:
            return 0.0

        avg_len = sum(len(s) for s in sentences) / len(sentences)

        # 中文平均句长 15-30 字为最佳
        if 15 <= avg_len <= 30:
            return 10.0
        elif avg_len < 15:
            return max(0.0, avg_len / 15 * 10)
        else:
            return max(0.0, 10 - (avg_len - 30) / 30 * 10)

    @staticmethod
    def _generate_suggestions(**scores: float) -> list[str]:
        """根据各维度评分生成改进建议。"""
        suggestions: list[str] = []
        if scores.get("punchline_density", 10) < 5:
            suggestions.append("笑点密度偏低，建议增加包袱、反转或意外元素。")
        if scores.get("dialogue_ratio", 10) < 5:
            suggestions.append("对话占比不足，建议增加角色对白，减少旁白叙述。")
        if scores.get("structure_completeness", 10) < 5:
            suggestions.append("结构不够完整，建议明确起承转合，增强叙事节奏。")
        if scores.get("word_diversity", 10) < 5:
            suggestions.append("词汇重复较多，建议丰富用词，避免同一表达反复出现。")
        if scores.get("colloquial_score", 10) < 5:
            suggestions.append("口语化程度不足，建议加入更多日常口语表达，让对白更自然。")
        if scores.get("length_score", 10) < 5:
            suggestions.append("长度不太合适当前剧本类型，建议调整篇幅。")
        if scores.get("readability", 10) < 5:
            suggestions.append("句子过长或过短，建议调整句长分布，提升阅读流畅度。")
        if not suggestions:
            suggestions.append("剧本整体质量不错，可在细节打磨上继续精进。")
        return suggestions
