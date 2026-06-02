"""v2 MemoryManager — 統一記憶體管理.

依據 §3.13 (Memory Layer) + 原則 23（業務模組不直接存取 memory）定義：
- 純協調器：零 LLM 呼叫、零 prompt 建構、零 JSON 解析
- 公開 API：add / retrieve / flush / get_context
- flush() 改為回傳 Result（涉及 ChromaDB 外部 I/O）
- 所有 LLM 邏輯轉發給 summarizer
"""

import logging
import time
from typing import Any, Dict, List, Optional

import config as config
from core.health import log_action
from memory.buffer import ConversationBuffer
from models.blueprints import Result

logger = logging.getLogger(__name__)


class MemoryManager:
    """統一記憶體管理：整合 buffer、摘要、RAG 檢索、批量萃取。

    設計原則：
    - 純協調器：零 LLM 呼叫、零 prompt 建構、零 JSON 解析
    - 所有 LLM 邏輯轉發給 summarizer
    - flush() 涉及 ChromaDB 外部 I/O，回傳 Result
    """

    def __init__(
        self,
        call_embedding_func: Any,
        vector_store: Any,
        summary_store: Any,
        temp_cache: Any = None,
        summarizer: Any = None,
    ) -> None:
        self.call_embedding_func = call_embedding_func
        self.vector_store = vector_store
        self.summary_store = summary_store
        self.temp_cache = temp_cache
        self.summarizer = summarizer

        # 內部 buffer
        self.buffer = ConversationBuffer()

        # 批次摘要時間追蹤
        self.last_batch_time: float = time.time()

        # session 管理
        self.current_session_id: Optional[str] = None

        # repair_consistency 計數器
        self._flush_count: int = 0

    # ------------------------------------------------------------------ #
    #  公開 API
    # ------------------------------------------------------------------ #

    def add(self, role: str, content: str) -> None:
        """寫入一則對話（內部會自動觸發 buffer.check token limit）"""
        self.buffer.add(role, content)

    def get_context(self) -> Dict[str, Any]:
        """回傳當前上下文（純資料，不含 RAG）"""
        return {
            "context": self.buffer.get() or [],
            "summary": self.summary_store.get_summary() if self.summary_store else "",
        }

    def serialize_context(self) -> str:
        """將 context 序列化為 str（供 responder.reply_simple 使用）"""
        return self.buffer.serialize()

    async def flush(self) -> Result:
        """觸發記憶壓縮（即時摘要 + 批量摘要兩個流程）。

        流程：
          1. 即時摘要：buffer.storage() → summarizer.summarize_turns() → 分流
          2. 批量摘要：TempCache 達閾值 → summarizer.batch_summarize() → vector
          3. 定期修復 consistency

        Returns:
            Result(success=True/False, data/error)
        """
        flushed = self.buffer.extract_flushed()
        if not flushed:
            return Result(success=True, data={"flushed_count": 0})

        # ─── 計數成功 flush，用於 repair_consistency 觸發 ───
        self._flush_count += 1

        # ─── 流程 1：即時摘要 ───
        immediate_ok = True
        try:
            await self._immediate_summarize(flushed)
        except Exception as e:
            logger.error("[MemoryManager] _immediate_summarize 異常：%s", e, exc_info=True)
            log_action("memory_manager", "immediate_summarize_exception", "DEGRADED", str(e), "記憶壓縮暫時不可用")
            immediate_ok = False

        # ─── 流程 2：批量摘要 ───
        batch_ok = True
        try:
            await self._batch_summarize_if_needed()
        except Exception as e:
            logger.error("[MemoryManager] _batch_summarize_if_needed 異常：%s", e, exc_info=True)
            batch_ok = False

        # ─── 流程 3：定期修復 consistency ───
        if self._flush_count >= config.VECTOR_REPAIR_INTERVAL:
            self._flush_count = 0
            if self.vector_store and hasattr(self.vector_store, "repair_consistency"):
                try:
                    repair_result = self.vector_store.repair_consistency()
                    logger.info("[MemoryManager] repair_consistency 完成：%s", repair_result)
                except Exception as e:
                    logger.error("[MemoryManager] repair_consistency 執行失敗：%s", e, exc_info=True)
                    log_action("memory_manager", "repair_consistency_failed", "DEGRADED", str(e), "記憶體修復暫時不可用")

        if immediate_ok and batch_ok:
            return Result(success=True, data={"flushed_count": len(flushed)})
        else:
            return Result(success=False, error="flush 部分流程失敗")

    async def retrieve(self, query: str, top_k: int = 1, min_similarity: float = 0.5) -> str:
        """RAG 檢索（整合原 Retriever 的邏輯）。

        Args:
            query: 查詢字串
            top_k: 取回筆數
            min_similarity: 最低相似度閾值，預設 0.5
        """
        if not self.call_embedding_func or not self.vector_store:
            return ""

        result = await self.call_embedding_func(config.EMBEDDING_MODEL_NAME, query)
        if not result.success:
            return ""
        query_embedding = result.data
        search_results = self.vector_store.search(query_embedding, top_k=top_k)
        if not search_results:
            return ""

        query_similarity = self.vector_store.compare(query_embedding)
        if query_similarity < min_similarity:
            logger.debug(
                "[MemoryManager] retrieve: 相似度 %.2f 低於閾值 %.2f，捨棄",
                query_similarity, min_similarity
            )
            return ""

        first_result = search_results[0]
        return first_result if first_result else ""

    # ------------------------------------------------------------------ #
    #  即時摘要流程
    # ------------------------------------------------------------------ #

    async def _immediate_summarize(self, flushed: List[dict]) -> Optional[dict]:
        """協調 summarizer 產生摘要並分流。"""
        if not self.summarizer:
            logger.warning("[MemoryManager] 沒有 summarizer，跳過即時摘要")
            log_action("memory_manager", "no_summarizer", "DEGRADED", "summarizer 未注入", "即時摘要不可用")
            return None

        result = await self.summarizer.summarize_turns(self.summary_store, flushed)
        if not result.success:
            logger.error("[MemoryManager] summarizer.summarize_turns 失敗：%s", result.error)
            return None

        data = result.data
        summary_text = data.get("summary", "")
        embedding = data.get("embedding")

        if summary_text:
            if self.summary_store:
                self.summary_store.set_summary(summary_text)

        # ─── similarity：由 MemoryManager 獨立計算 ───
        similarity_score: float = 0.0
        if embedding is not None and self.vector_store:
            try:
                compare_result = self.vector_store.compare(embedding)
                if isinstance(compare_result, (int, float)):
                    similarity_score = float(compare_result)
                else:
                    logger.warning(
                        "[MemoryManager] vector_store.compare 返回非數值 %s，fallback 為 0.0",
                        type(compare_result).__name__
                    )
            except (TypeError, ValueError) as e:
                logger.info(
                    "[MemoryManager] vector_store.compare 拋出 %s：%s，fallback 為 0.0",
                    type(e).__name__, e
                )
            except Exception as e:
                logger.error(
                    "[MemoryManager] vector_store.compare 發生未預期的 %s：%s",
                    type(e).__name__, e
                )

        # ─── importance：由 summarizer 獨立評估 ───
        importance_result = await self.summarizer.check_importance(summary_text)
        importance_score = importance_result.data if importance_result.success else 0.5

        self._route_by_scores(summary_text, flushed, similarity_score, importance_score, embedding)
        log_action("memory", "immediate_summarize_complete", "OK")

        return data

    # ------------------------------------------------------------------ #
    #  分流邏輯（僅做決策，不含執行）
    # ------------------------------------------------------------------ #

    def _route_by_scores(
        self,
        summary_text: str,
        flushed: List[dict],
        similarity_score: float,
        importance_score: float,
        embedding: Optional[list] = None,
    ) -> None:
        """依雙維度分數分流."""
        if not summary_text:
            return

        # 1. 太相似 → 丟棄
        if similarity_score >= config.SIMILARITY_UPPER_BOUNDARY:
            logger.debug("[MemoryManager] 太相似，捨棄 (similarity: %.2f)", similarity_score)
            return

        # 2. 新且重要 → 向量庫
        if importance_score >= config.IMPORTANCE_HIGH:
            if embedding is not None and self.vector_store:
                try:
                    self.vector_store.add(summary_text, flushed, embedding)
                    logger.info("[MemoryManager] 高重要性摘要寫入向量庫 (importance: %.2f)", importance_score)
                except Exception as e:
                    logger.error("[MemoryManager] 寫入向量庫失敗：%s", e)
            elif self.vector_store:
                logger.warning("[MemoryManager] 高重要性但無 embedding，降級至 temp_cache")
                if self.temp_cache:
                    try:
                        self.temp_cache.add(
                            raw_chunk=flushed,
                            summary=summary_text,
                            similarity_score=similarity_score,
                            importance_score=importance_score,
                        )
                    except Exception as e:
                        logger.error("[MemoryManager] 寫入 TempCache 失敗：%s", e)
            return

        # 3. 新但中等重要性 → TempCache
        if importance_score >= config.IMPORTANCE_LOW and self.temp_cache:
            try:
                self.temp_cache.add(
                    raw_chunk=flushed,
                    summary=summary_text,
                    similarity_score=similarity_score,
                    importance_score=importance_score,
                )
            except Exception as e:
                logger.error("[MemoryManager] 寫入 TempCache 失敗：%s", e)
            return

        # 4. 不重要 → 丟棄
        logger.debug("[MemoryManager] 低重要性摘要捨棄 (importance: %.2f)", importance_score)

    # ------------------------------------------------------------------ #
    #  批量摘要流程
    # ------------------------------------------------------------------ #

    async def _batch_summarize_if_needed(self) -> None:
        """若 TempCache 達閾值，觸發批量摘要"""
        if not self.temp_cache:
            return

        idle_seconds = time.time() - self.last_batch_time
        idle_expired = idle_seconds >= config.TEMP_CACHE_IDLE_SECONDS
        token_exceeded = self.temp_cache.total_tokens() >= config.TEMP_CACHE_FORCE_TOKENS

        if not (idle_expired or token_exceeded):
            return

        items = self.temp_cache.get_top_k(config.TEMP_CACHE_TOP_K)
        if not items:
            return

        batch_result = await self.summarizer.batch_summarize(items) if self.summarizer else Result(success=False)
        if batch_result.success and batch_result.data:
            new_summary = batch_result.data.get("summary")
            batch_embedding = batch_result.data.get("embedding")
            if new_summary:
                all_raw_chunks: List[dict] = []
                for item in items:
                    chunk = item.get("raw_chunk", [])
                    if isinstance(chunk, list):
                        all_raw_chunks.extend(chunk)
                    elif isinstance(chunk, dict):
                        all_raw_chunks.append(chunk)

                write_success = False
                if batch_embedding is not None and self.vector_store:
                    try:
                        self.vector_store.add(new_summary, all_raw_chunks, batch_embedding)
                        write_success = True
                        logger.info("[MemoryManager] 批量萃取結果寫入向量庫成功")
                    except Exception as e:
                        logger.error("[MemoryManager] 批量摘要寫入向量庫失敗：%s", e)

                if write_success:
                    log_action("memory", "batch_summarize_complete", "OK")
                    for item in items:
                        self.temp_cache.remove(item["id"])

        self.last_batch_time = time.time()
