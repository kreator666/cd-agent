"""RAG Retriever —— 混合检索与上下文注入。

预留接口，将在任务 3.x 中实现。
"""


class ComedyRetriever:
    """喜剧知识库检索器。"""

    def retrieve(self, query: str, top_k: int = 5) -> list[str]:
        """检索与查询相关的喜剧知识片段。

        Args:
            query: 用户查询。
            top_k: 返回结果数量。

        Returns:
            list[str]: 相关知识片段列表。
        """
        raise NotImplementedError("将在第三阶段实现。")
