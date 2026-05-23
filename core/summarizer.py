"""Summarizer — 記憶壓縮（從 core/orchestrator.py 抽取 summarize）"""

import json
import re
import config
from typing import Any, List
from clients.message_builder import MessageBuilder


class Summarizer:
    """Summarizer：對話摘要與向量存入"""

    def __init__(
        self,
        call_model_func: Any,
        call_embedding_func: Any,
        summary: Any,
        vector: Any,
        temp_cache: Any = None,
    ) -> None:
        self.call_model_func = call_model_func
        self.call_embedding_func = call_embedding_func
        self.summary = summary
        self.vector = vector
        self.temp_cache = temp_cache

    async def summarize(self, flushed: List[dict]) -> None:
        """記憶壓縮：先 LLM 產生摘要，成功後再移除 flushed 資料"""
        if not flushed:
            return

        turns = self._format_turns(flushed)
        summary_msgs = MessageBuilder.build_meta(config.SUMMARY_PROMPT, {
            "OLD_SUMMARY": self.summary.get_summary(),
            "CONVERSATION": "\n".join(turns),
        })

        # 先呼叫 LLM，失敗則不執行 add_cache，資料保留在 buffer
        summary_text, _ = await self._call_llm(config.MEDIUM_MODEL_NAME, summary_msgs, caller="summarizer")

        # LLM 成功後才移除 flushed 資料
        self.summary.add_cache(flushed)
        self.summary.set_summary(summary_text)

        embedded = await self.call_embedding_func(config.EMBEDDING_MODEL_NAME, summary_text)
        similarity_score = self.vector.compare(embedded)

        # similarity_score 原始範圍 0.5~1.5，正規化到 0~1
        normalized_similarity = (similarity_score - 0.5) / 1.0

        importance_score = await self._check_importance(summary_text)
        confidence = (normalized_similarity + importance_score) / 2

        if confidence > config.TEMP_CACHE_HIGH_CONFIDENCE:
            # 高置信 → 存入向量庫
            self.vector.add(summary_text, flushed, embedded)
        elif confidence < config.TEMP_CACHE_LOW_CONFIDENCE:
            # 低置信 → 丟棄
            pass
        elif self.temp_cache:
            # 中間區 → 進入 Temp Cache
            self.temp_cache.add(
                raw_chunk=flushed,
                summary=summary_text,
                similarity_score=similarity_score,
                importance_score=importance_score,
            )

    def _format_turns(self, flushed: List[dict]) -> List[str]:
        """格式化對話輪廓"""
        return [
            f"{'用戶' if r['role'] == 'user' else '助理'}：{r['content']}"
            for r in flushed
        ]

    async def _call_llm(self, model: str, messages: List[dict], caller: str) -> tuple[str, Any]:
        """呼叫語言模型"""
        return await self.call_model_func(
            model, messages,
            config.SUMMARY_TEMPERATURE,
            config.SUMMARY_MAX_TOKENS,
            False,
            caller=caller,
        )

    async def _check_importance(self, summary: str) -> float:
        """檢查摘要重要性，回傳值 clamp 到 0~1"""
        check_msgs = MessageBuilder.build_meta(config.IMPORTANCE_PROMPT, {
            "SUMMARY": summary,
        })
        check_result, _ = await self._call_llm(config.MEDIUM_MODEL_NAME, check_msgs, caller="summarizer")

        match = re.search(r'\d+\.?\d*', check_result)
        raw_score = float(match.group()) if match else 0.0
        return max(0.0, min(1.0, raw_score))
