"""知识系统数据模型。

定义喜剧理论知识的结构化表示，供知识蒸馏、向量检索和创作节点使用。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EntityTriple(BaseModel):
    """知识图谱三元组：实体 - 关系 - 实体。"""

    subject: str = Field(description="主语实体")
    relation: str = Field(description="关系")
    object: str = Field(description="宾语实体")


class KnowledgeItem(BaseModel):
    """单条理论知识条目。

    可由知识蒸馏器从理论文本中提取，也可由向量检索器返回。
    """

    id: str = Field(description="条目唯一标识，建议短横线连接的小写英文名")
    title: str = Field(description="条目标题")
    category: Literal["concept", "technique", "pattern", "rule"] = Field(
        description="条目类别：概念 / 技法 / 结构模板 / 规则"
    )
    content: str = Field(description="原始内容或详细说明")
    summary: str = Field(default="", description="一句话摘要")
    source: str = Field(default="", description="来源文档或章节")
    entity_triples: list[EntityTriple] = Field(
        default_factory=list, description="相关知识图谱三元组"
    )
    related_terms: list[str] = Field(
        default_factory=list, description="相关术语或别名"
    )
    embedding_text: str = Field(
        default="", description="用于向量化的文本，由标题、摘要、内容和术语拼接而成"
    )

    def build_embedding_text(self) -> str:
        """若未指定 embedding_text，则自动拼接生成。"""
        if self.embedding_text:
            return self.embedding_text
        parts = [self.title, self.summary, self.content]
        if self.related_terms:
            parts.append("相关术语：" + "、".join(self.related_terms))
        return "\n".join(p for p in parts if p)


class DistillationOutput(BaseModel):
    """知识蒸馏器的一次性输出结构。"""

    items: list[KnowledgeItem] = Field(description="提取出的知识条目列表")
