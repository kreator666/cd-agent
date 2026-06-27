"""段子标注流水线核心。

Phase 4 数据增强：将原始脱口秀文本清洗、切分、标注，输出结构化示例，
供后续 ExampleRetriever 做 Few-shot 注入。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field, field_validator

from comedy_agent.models.factory import ModelFactory

logger = logging.getLogger(__name__)

DEFAULT_ANNOTATION_PROMPT = """你是一位喜剧标注专家。请分析下面这段脱口秀文本，提取关键创作要素。

要求：
1. setup：铺垫部分，引发共鸣或建立预期的内容。
2. punchline：笑点/反转部分。
3. callback：是否有 callback（后文呼应前文的细节）。
4. tags：3-5 个关键词标签。
5. topic：核心话题（10 字以内）。
6. style：风格，如自嘲/观察/讽刺/吐槽/荒诞。
7. structure_type：结构类型，如 script/one_liner/story。
8. humor_score：幽默程度 1-10。

文本：
{text}
"""


class AnnotatedExample(BaseModel):
    """单条标注后的段子示例。"""

    example_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="唯一标识",
    )
    content: str = Field(description="完整段子文本")
    setup: str = Field(default="", description="铺垫部分")
    punchline: str = Field(default="", description="笑点/反转")
    callback: bool = Field(default=False, description="是否包含 callback")
    callback_to: str | None = Field(default=None, description="callback 呼应的对象（可选）")
    tags: list[str] = Field(default_factory=list, description="关键词标签")
    topic: str = Field(default="", description="核心话题")
    style: str = Field(default="", description="风格")
    kind: str = Field(default="standup", description="喜剧种类")
    structure_type: str = Field(default="script", description="结构类型")
    humor_score: float = Field(
        default=5.0,
        ge=1.0,
        le=10.0,
        description="幽默评分 1-10",
    )
    source: str = Field(default="", description="来源文件/作品")
    embedding_text: str = Field(default="", description="用于向量检索的拼接文本")

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, v):
        if isinstance(v, str):
            return [t.strip() for t in v.replace("，", ",").split(",") if t.strip()]
        return v or []


def build_embedding_text(example: AnnotatedExample) -> str:
    """将标注结果组装成适合向量检索的文本。"""
    parts = [
        f"话题：{example.topic}",
        f"风格：{example.style}",
        f"结构：{example.structure_type}",
        f"标签：{'/'.join(example.tags)}",
        f"铺垫：{example.setup}",
        f"笑点：{example.punchline}",
        f"文本：{example.content}",
    ]
    return "\n".join(parts)


def _clean_text(text: str) -> str:
    """清洗单条文本。"""
    text = text.strip()
    # 合并多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def split_text_into_segments(text: str) -> list[str]:
    """将长文本按空行切分为候选段子段落。"""
    segments = []
    for block in text.split("\n\n"):
        cleaned = _clean_text(block)
        if len(cleaned) >= 10:
            segments.append(cleaned)
    return segments


def _default_llm(model: str | None = None) -> BaseChatModel:
    """获取默认标注模型。"""
    return ModelFactory.get_model(model, task_type="analytical")


def annotate_text(
    text: str,
    llm: BaseChatModel | None = None,
    model: str | None = None,
    kind: str = "standup",
    style: str | None = None,
    source: str = "",
    prompt_template: str = DEFAULT_ANNOTATION_PROMPT,
) -> AnnotatedExample:
    """对单条段子文本进行标注。

    Args:
        text: 原始段子文本。
        llm: 可选外部 LLM；为 None 时使用 ModelFactory 获取。
        model: 模型名称，仅当 llm 为 None 时生效。
        kind: 喜剧种类。
        style: 默认风格。
        source: 来源标识。
        prompt_template: 标注 Prompt 模板。

    Returns:
        标注后的 AnnotatedExample。
    """
    text = _clean_text(text)
    if llm is None:
        llm = _default_llm(model)

    prompt = prompt_template.format(text=text)
    try:
        structured = llm.with_structured_output(AnnotatedExample)
        result = structured.invoke([("human", prompt)])
    except Exception as e:
        logger.warning("结构化标注失败，回退到默认标注: %s", e)
        result = AnnotatedExample(content=text)

    # 回填/修正固定字段
    result_dict = result.model_dump() if isinstance(result, BaseModel) else dict(result)
    result_dict["content"] = text
    result_dict["kind"] = kind
    if style:
        result_dict["style"] = style
    result_dict["source"] = source

    example = AnnotatedExample(**result_dict)
    example.embedding_text = build_embedding_text(example)
    return example


def process_texts(
    segments: list[str],
    llm: BaseChatModel | None = None,
    model: str | None = None,
    kind: str = "standup",
    style: str | None = None,
    source: str = "",
) -> list[AnnotatedExample]:
    """批量标注文本段落。"""
    examples: list[AnnotatedExample] = []
    for idx, seg in enumerate(segments):
        logger.info("标注第 %d/%d 段", idx + 1, len(segments))
        try:
            ex = annotate_text(
                seg,
                llm=llm,
                model=model,
                kind=kind,
                style=style,
                source=source,
            )
            examples.append(ex)
        except Exception as e:
            logger.warning("第 %d 段标注失败: %s", idx + 1, e)
    return examples


def load_raw_segments(path: Path) -> list[tuple[str, str]]:
    """从文件或目录加载原始段落。

    Returns:
        [(source, segment_text), ...]
    """
    path = Path(path)
    results: list[tuple[str, str]] = []

    if path.is_file():
        if path.suffix.lower() in (".json", ".jsonl"):
            results.extend(_load_jsonl(path))
        else:
            text = path.read_text(encoding="utf-8")
            for seg in split_text_into_segments(text):
                results.append((str(path), seg))
    elif path.is_dir():
        for file_path in sorted(path.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() in (".json", ".jsonl"):
                results.extend(_load_jsonl(file_path))
            elif file_path.suffix.lower() in (".txt", ".md"):
                text = file_path.read_text(encoding="utf-8")
                for seg in split_text_into_segments(text):
                    results.append((str(file_path), seg))

    return results


def _load_jsonl(path: Path) -> list[tuple[str, str]]:
    """读取 JSON/JSONL 文件，提取 content/text 字段。"""
    results: list[tuple[str, str]] = []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return results

    records: list[dict[str, Any]] = []
    if text.startswith("["):
        try:
            records = json.loads(text)
        except json.JSONDecodeError:
            pass
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    for record in records:
        content = record.get("content") or record.get("text") or ""
        if content and len(content) >= 10:
            results.append((str(path), content))
    return results


def save_annotations(examples: list[AnnotatedExample], output_path: Path) -> None:
    """将标注结果保存为 JSONL。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [ex.model_dump_json(ensure_ascii=False) for ex in examples]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("已保存 %d 条标注到 %s", len(examples), output_path)


def generate_schema_json() -> dict[str, Any]:
    """生成标注 Schema（JSON Schema 格式）。"""
    return AnnotatedExample.model_json_schema()
