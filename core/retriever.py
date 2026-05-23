"""Retriever — RAG 查詢與檢索"""

import config
from typing import Any


class Retriever:
    """RAG 檢索器：embedding + vector search"""

    def __init__(self, call_embedding_func: Any, vector: Any) -> None:
        self.call_embedding_func = call_embedding_func
        self.vector = vector

    async def retrieve(self, query: str, top_k: int = 1) -> str:
        """根據 query 進行向量搜尋並回傳檢索結果

        Args:
            query: 查詢字串
            top_k: 回傳結果數量

        Returns:
            檢索結果字串
        """
        if not self.call_embedding_func or not self.vector:
            return ""

        query_vector = await self.call_embedding_func(config.EMBEDDING_MODEL_NAME, query)
        search_results = self.vector.search(query_vector, top_k=top_k)
        return search_results[0] if search_results else ""
