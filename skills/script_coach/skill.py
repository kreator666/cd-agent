"""段子教练 Skill —— 顶流参照 + 自动评分 + 循环优化。

基于已入库的顶流脱口秀文稿（collection: top_tier_scripts），
对新产出段子进行多维度对比评分，指出差距并自动迭代优化，
最终返回成品与完整评分记录。最终作品存入用户作品库，
不会混入顶流文稿库。
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from comedy_agent.skills.base import ComedySkill
from comedy_agent.models.factory import ModelFactory
from comedy_agent.rag.vector_store import VectorStore
from comedy_agent.core.config import settings
from comedy_agent.memory.models import ScriptData

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "top_tier_scripts"
MAX_ITERATIONS = 5


class DimensionScores(BaseModel):
    """单轮多维度评分。"""

    humor_score: float = Field(default=5.0, ge=1.0, le=10.0)
    setup_quality: float = Field(default=5.0, ge=1.0, le=10.0)
    punchline_quality: float = Field(default=5.0, ge=1.0, le=10.0)
    pacing: float = Field(default=5.0, ge=1.0, le=10.0)
    colloquial_score: float = Field(default=5.0, ge=1.0, le=10.0)
    resonance: float = Field(default=5.0, ge=1.0, le=10.0)
    surprise: float = Field(default=5.0, ge=1.0, le=10.0)
    observation: float = Field(default=5.0, ge=1.0, le=10.0)
    structure_integrity: float = Field(default=5.0, ge=1.0, le=10.0)
    performance_readiness: float = Field(default=5.0, ge=1.0, le=10.0)

    def overall(self) -> float:
        """综合均分。"""
        return round(sum(self.model_dump().values()) / len(self.model_dump()), 2)


class CoachRoundResult(BaseModel):
    """单轮教练结果。"""

    round: int = Field(description="第几轮")
    script: str = Field(description="本轮待评/优化后的段子正文")
    dimension_scores: DimensionScores = Field(default_factory=DimensionScores)
    overall_score: float = Field(default=0.0, ge=1.0, le=10.0)
    gap_to_top: str = Field(default="", description="与顶流文稿的主要差距")
    weaknesses: list[str] = Field(default_factory=list, description="可改进点")
    improvement_plan: str = Field(default="", description="下一轮改写方向")
    references: list[dict[str, Any]] = Field(default_factory=list, description="参考文稿摘要")


class CoachResult(BaseModel):
    """段子教练完整输出。"""

    final_script: str = Field(description="最终成品段子")
    stopped_reason: str = Field(description="结束原因")
    iterations: list[CoachRoundResult] = Field(default_factory=list)
    saved_script_id: str | None = Field(default=None, description="保存到作品库的 script_id")


class DiagnosisOutput(BaseModel):
    """单轮差距诊断与改进建议。"""

    gap_to_top: str = Field(description="与顶流文稿的主要差距")
    weaknesses: list[str] = Field(description="可改进点，3-5 条")
    improvement_plan: str = Field(description="下一轮具体改写方向")


class ReferenceInfo(BaseModel):
    """参考文稿信息。"""

    source: str = Field(default="")
    topic: str = Field(default="")
    style: str = Field(default="")
    humor_score: float = Field(default=5.0)
    snippet: str = Field(default="", description="原文摘要（前 300 字）")


class ScriptCoachArgs(BaseModel):
    """段子教练参数 Schema。"""

    script: str = Field(description="待打磨的脱口秀初稿")
    topic: str = Field(description="核心话题")
    style: str = Field(default="日常观察", description="目标风格")
    target_duration: int = Field(default=3, ge=1, le=20, description="目标时长（分钟）")
    iterations: int = Field(default=1, ge=1, le=100, description="最大迭代轮数，1-5（运行时强制限制为 5）")
    min_score: float = Field(default=8.0, ge=1.0, le=10.0, description="提前终止的综合分阈值")
    top_k: int = Field(default=5, ge=1, le=20, description="检索顶流文稿数量")
    save_product: bool = Field(default=True, description="是否保存最终成品到用户作品库")
    user_id: str | None = Field(default=None, description="用户标识（保存作品时用）")


class ScriptCoachSkill(ComedySkill):
    """段子教练 Skill。

    对输入段子按顶流标准打分、找差距、循环优化。
    """

    task_type: str = "analytical"
    name: str = "script_coach"
    available_styles: ClassVar[list[str]] = ["日常观察", "自嘲", "社会讽刺", "职场", "黑色幽默", "吐槽"]
    description: str = (
        "段子教练。输入一段脱口秀初稿，自动与顶流文稿库对比、按维度打分、"
        "指出可改进点，并循环优化至多 5 轮，最终返回成品与完整迭代记录。"
    )
    args_schema: type[BaseModel] = ScriptCoachArgs

    # 顶流文稿库集合名
    top_tier_collection: str = DEFAULT_COLLECTION

    def _run(
        self,
        script: str,
        topic: str,
        style: str = "日常观察",
        target_duration: int = 3,
        iterations: int = 1,
        min_score: float = 8.0,
        top_k: int = 5,
        save_product: bool = True,
        user_id: str | None = None,
    ) -> str:
        iterations = min(iterations, MAX_ITERATIONS)
        current_script = script.strip()

        results: list[CoachRoundResult] = []
        stopped_reason = ""
        saved_script_id: str | None = None

        for round_num in range(1, iterations + 1):
            references = self._retrieve_top_tier_references(
                current_script, topic, style, top_k=top_k
            )
            round_result = self._evaluate_round(
                round_num=round_num,
                script=current_script,
                topic=topic,
                style=style,
                target_duration=target_duration,
                references=references,
            )
            results.append(round_result)

            if round_result.overall_score >= min_score:
                stopped_reason = f"第 {round_num} 轮达到 min_score 阈值 {min_score}"
                break

            if round_num == iterations:
                stopped_reason = f"达到最大迭代轮数 {iterations}"
                break

            # 根据改进建议生成下一版
            current_script = self._rewrite_script(
                current_script=current_script,
                topic=topic,
                style=style,
                target_duration=target_duration,
                round_result=round_result,
                references=references,
            )

        final_script = current_script

        # 保存最终作品到用户作品库（绝不写入顶流库）
        if save_product and user_id and self.memory is not None:
            try:
                script_data = ScriptData(
                    title=f" coached: {topic}",
                    content=final_script,
                    script_type="standup",
                    rating=round(results[-1].overall_score / 2, 1) if results else None,  # 5 分制
                    tags=[topic, style, "script_coach"],
                )
                saved = self.memory.save_script(user_id, script_data)
                saved_script_id = saved.script_id
            except Exception as e:
                logger.warning("保存最终作品到用户库失败: %s", e)

        coach_result = CoachResult(
            final_script=final_script,
            stopped_reason=stopped_reason,
            iterations=results,
            saved_script_id=saved_script_id,
        )
        return json.dumps(coach_result.model_dump(), ensure_ascii=False, indent=2)

    async def _arun(
        self,
        script: str,
        topic: str,
        style: str = "日常观察",
        target_duration: int = 3,
        iterations: int = 1,
        min_score: float = 8.0,
        top_k: int = 5,
        save_product: bool = True,
        user_id: str | None = None,
    ) -> str:
        return self._run(
            script, topic, style, target_duration, iterations, min_score, top_k, save_product, user_id
        )

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #
    def _get_top_tier_store(self) -> VectorStore:
        """获取顶流文稿向量库。"""
        return VectorStore(
            collection_name=self.top_tier_collection,
            persist_path=str(settings.vector_db_path),
        )

    def _retrieve_top_tier_references(
        self,
        script: str,
        topic: str,
        style: str,
        top_k: int = 5,
    ) -> list[ReferenceInfo]:
        """检索与当前段子最相关的顶流文稿。"""
        store = self._get_top_tier_store()
        query = f"{topic} {style}\n{script[:500]}"
        filter_dict: dict[str, Any] | None = None
        if style:
            filter_dict = {"style": style}

        try:
            docs = store.search(query, top_k=top_k, filter_dict=filter_dict)
        except Exception as e:
            logger.warning("顶流文稿库检索失败: %s", e)
            return []

        references: list[ReferenceInfo] = []
        for doc in docs:
            meta = doc.metadata or {}
            content = meta.get("content") or doc.page_content
            references.append(
                ReferenceInfo(
                    source=str(meta.get("source", "未知来源")),
                    topic=str(meta.get("topic", "")),
                    style=str(meta.get("style", "")),
                    humor_score=float(meta.get("humor_score", 5.0)),
                    snippet=content[:300],
                )
            )
        return references

    @staticmethod
    def _format_references(references: list[ReferenceInfo]) -> str:
        """将参考文稿格式化为 Prompt 文本。"""
        if not references:
            return "（当前顶流文稿库为空，请仅依据通用脱口秀标准评分）"
        lines: list[str] = []
        for idx, ref in enumerate(references, 1):
            lines.append(
                f"[{idx}] 来源：{ref.source} | 话题：{ref.topic} | 风格：{ref.style} | "
                f"幽默分：{ref.humor_score}\n{ref.snippet}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _invoke_structured(
        llm: Any,
        schema: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        default: BaseModel,
    ) -> BaseModel:
        """优先使用 with_structured_output，失败时回退到 JSON 文本解析。

        部分模型/地区对 structured output 返回 403，使用普通 ChatCompletion
        并要求模型输出 JSON，可在多数场景下降级恢复。
        """
        try:
            structured_llm = llm.with_structured_output(schema)
            return structured_llm.invoke(
                [("system", system_prompt), ("human", user_prompt)]
            )
        except Exception as e:
            logger.warning("结构化输出失败，尝试 JSON 文本解析: %s", e)

        # Fallback：使用普通 ChatCompletion 并要求模型输出 JSON
        json_system = (
            system_prompt + "\n\n请严格按 JSON 格式输出，不要附加任何解释或 markdown 代码块。"
        )
        json_user = user_prompt + "\n\n请直接输出符合上述 Schema 的 JSON 对象。"
        try:
            response = llm.invoke([("system", json_system), ("human", json_user)])
            text = str(getattr(response, "content", response)).strip()
            # 去除可能的 markdown 代码围栏
            if text.startswith("```"):
                text = (
                    text.removeprefix("```json")
                    .removeprefix("```")
                    .removesuffix("```")
                    .strip()
                )
            data = json.loads(text)
            return schema(**data)
        except Exception as e:
            logger.warning("JSON 文本解析也失败，使用默认: %s", e)
            return default

    def _evaluate_round(
        self,
        round_num: int,
        script: str,
        topic: str,
        style: str,
        target_duration: int,
        references: list[ReferenceInfo],
    ) -> CoachRoundResult:
        """对单轮段子进行评分和诊断。"""
        system_prompt = (
            "你是一位资深脱口秀教练。你的任务是把学员的新段子与顶流脱口秀文稿做标准对比，"
            "按维度给出客观评分和可落地的改进建议。\n\n"
            "评分维度（每项 1–10 分）：\n"
            "- humor_score：整体幽默程度\n"
            "- setup_quality：铺垫建立预期质量\n"
            "- punchline_quality：笑点/反转质量\n"
            "- pacing：节奏紧凑度\n"
            "- colloquial_score：口语化/舞台感\n"
            "- resonance：观众共鸣感\n"
            "- surprise：意外感/预期违背\n"
            "- observation：观察角度独特性\n"
            "- structure_integrity：结构完整性\n"
            "- performance_readiness：可直接上演度\n\n"
            "打分原则：6 分=普通开放麦水准；8 分=成熟商演水准；9-10 分=顶流专场水准。\n"
            "请严格按 JSON 格式输出，不要附加解释。"
        )
        user_prompt = (
            f"请对以下脱口秀段子进行教练式评审。\n\n"
            f"【待评审段子】\n{script}\n\n"
            f"【话题】{topic}\n"
            f"【风格】{style}\n"
            f"【目标时长】约 {target_duration} 分钟\n\n"
            f"【参考顶流文稿】\n{self._format_references(references)}"
        )

        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        scores = self._invoke_structured(
            llm,
            DimensionScores,
            system_prompt,
            user_prompt,
            DimensionScores(),
        )

        # 用另一个结构化调用生成诊断与改进建议
        diagnosis = self._diagnose_round(
            script=script,
            topic=topic,
            style=style,
            target_duration=target_duration,
            references=references,
            scores=scores,
        )

        return CoachRoundResult(
            round=round_num,
            script=script,
            dimension_scores=scores,
            overall_score=scores.overall(),
            gap_to_top=diagnosis.get("gap_to_top", ""),
            weaknesses=diagnosis.get("weaknesses", []),
            improvement_plan=diagnosis.get("improvement_plan", ""),
            references=[ref.model_dump() for ref in references],
        )

    def _diagnose_round(
        self,
        script: str,
        topic: str,
        style: str,
        target_duration: int,
        references: list[ReferenceInfo],
        scores: DimensionScores,
    ) -> dict[str, Any]:
        """生成差距诊断和改进建议。"""
        system_prompt = (
            "你是一位资深脱口秀教练。请根据已给出的多维度评分，指出段子与顶流水准的差距，"
            "并给出 3-5 条具体可改进点，以及下一轮改写的明确方向。\n"
            "请严格按 JSON 格式输出，不要附加解释。"
        )
        scores_text = json.dumps(scores.model_dump(), ensure_ascii=False)
        user_prompt = (
            f"【待诊断段子】\n{script}\n\n"
            f"【话题】{topic}\n【风格】{style}\n【目标时长】约 {target_duration} 分钟\n\n"
            f"【维度评分】{scores_text}\n\n"
            f"【参考顶流文稿】\n{self._format_references(references)}"
        )

        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type=self.task_type)
        diagnosis_result = self._invoke_structured(
            llm,
            DiagnosisOutput,
            system_prompt,
            user_prompt,
            DiagnosisOutput(
                gap_to_top="（诊断生成失败）",
                weaknesses=["请检查铺垫是否过长", "笑点是否足够意外", "口语化是否自然"],
                improvement_plan="优化铺垫节奏，增强笑点意外感，让表达更口语化。",
            ),
        )
        return diagnosis_result.model_dump()

    def _rewrite_script(
        self,
        current_script: str,
        topic: str,
        style: str,
        target_duration: int,
        round_result: CoachRoundResult,
        references: list[ReferenceInfo],
    ) -> str:
        """根据改进建议生成下一版段子。"""
        system_prompt = (
            "你是一位顶尖脱口秀编剧。请根据教练给出的评分、差距和改进建议，"
            "对当前段子进行大刀阔斧的改写。要求：\n"
            "1. 保留原话题和核心观点；\n"
            "2. 保留原文中最精彩的 1-2 个句子，其余允许彻底重写；\n"
            "3. 针对 weaknesses 逐项改进，必须做出肉眼可见的变化，禁止只做同义词替换或调整语序；\n"
            "4. 至少完成 3 处明显改动：口语化重构、节奏压缩、笑点升级、加入具象画面或反转；\n"
            "5. 输出必须是连续、干净的纯文本段子正文，不要分析、不要格式标签、不要分段标题。"
        )
        user_prompt = (
            f"【话题】{topic}\n"
            f"【风格】{style}\n"
            f"【目标时长】约 {target_duration} 分钟\n\n"
            f"【当前段子】\n{current_script}\n\n"
            f"【本轮评分】{round_result.overall_score}/10\n"
            f"【主要差距】{round_result.gap_to_top}\n"
            f"【可改进点】\n" + "\n".join(f"- {w}" for w in round_result.weaknesses) + "\n\n"
            f"【改写方向】{round_result.improvement_plan}\n\n"
            f"【参考顶流文稿】\n{self._format_references(references)}\n\n"
            f"请直接输出改写后的段子正文。"
        )

        llm = ModelFactory.get_model_with_fallback(name=self.model_name, task_type="creative")
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", user_prompt),
        ])
        chain = prompt | llm
        try:
            result = chain.invoke({})
            text = str(result.content) if hasattr(result, "content") else str(result)
            return text.strip()
        except Exception as e:
            logger.warning("改写生成失败，返回当前版本: %s", e)
            return current_script


def main() -> int:
    """CLI 入口，便于独立调试。"""
    import argparse

    parser = argparse.ArgumentParser(description="段子教练 Skill CLI")
    parser.add_argument("--script", required=True, help="待打磨的段子文件路径或直接文本")
    parser.add_argument("--topic", required=True, help="核心话题")
    parser.add_argument("--style", default="日常观察", help="目标风格")
    parser.add_argument("--target-duration", type=int, default=3, help="目标时长（分钟）")
    parser.add_argument("--iterations", type=int, default=1, help="最大迭代轮数 1-5")
    parser.add_argument("--min-score", type=float, default=8.0, help="提前终止阈值")
    parser.add_argument("--top-k", type=int, default=5, help="检索顶流文稿数量")
    parser.add_argument("--model", default=None, help="覆盖模型名称")
    args = parser.parse_args()

    script_text = args.script
    if len(script_text) < 200 and Path(script_text).exists():
        script_text = Path(script_text).read_text(encoding="utf-8")

    skill = ScriptCoachSkill()
    if args.model:
        skill.model_name = args.model
    output = skill.invoke(
        {
            "script": script_text,
            "topic": args.topic,
            "style": args.style,
            "target_duration": args.target_duration,
            "iterations": args.iterations,
            "min_score": args.min_score,
            "top_k": args.top_k,
            "save_product": False,
        }
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
