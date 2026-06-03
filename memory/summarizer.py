"""v2 ConversationSummarizer — LLM 摘要生成器.

依據 §3.13 (Memory Layer) 定義：
- 所有 LLM 邏輯（摘要生成、重要性評估、batch 合併）集中在此類別
- 由 MemoryManager 協調呼叫，不直接存取記憶儲存
- 所有公開 API 回傳 Result（不拋異常）
- 符合 v2 logging 規範
"""

import logging
import re
from typing import Any, List, Optional

import config
from core.health import log_action
from core.json_utils import parse_first_json
from core.prompts import BATCH_SUMMARY_PROMPT, IMPORTANCE_PROMPT, SUMMARY_PROMPT
from models.blueprints import Result

logger = logging.getLogger(__name__)


class ConversationSummarizer:
    """LLM 摘要生成器：所有 LLM 邏輯在此.

    設計原則：
    - 不直接存取 ConversationSummary（純資料）
    - 不直接存取 Vector/TempCache（由 MemoryManager 處理）
    - 只負責：呼叫 LLM、解析結果、回傳 data
    """

    def __init__(
        self,
        call_model_func: Any,
        call_embedding_func: Any,
    ) -> None:
        self.call_model_func = call_model_func
        self.call_embedding_func = call_embedding_func

    async def summarize_turns(
        self,
        summary_store: Any,
        flushed: List[dict],
    ) -> Result:
        """即時摘要一輪對話.

        Args:
            summary_store: ConversationSummary（僅讀取 get_summary()）
            flushed: 寫入 buffer 的原始訊息

        Returns:
            Result(data={"summary": str, "embedding": list | None})
            Result(success=False, error=str)
        """
        if not flushed or not self.call_model_func:
            return Result(success=False, error="empty flushed or no model func")

        turns = [
            f"{'用戶' if r['role'] == 'user' else '助理'}：{r['content']}"
            for r in flushed
        ]
        conversation_text = "\n".join(turns)

        old_summary = summary_store.get_summary() if summary_store else ""

        prompt = SUMMARY_PROMPT.format(
            OLD_SUMMARY=old_summary,
            CONVERSATION=conversation_text,
        )
        messages = [{"role": "user", "content": prompt}]

        result_obj = await self.call_model_func(
            config.MEDIUM_MODEL_NAME,
            messages,
            config.SUMMARY_TEMPERATURE,
            config.SUMMARY_MAX_TOKENS,
            False,
            caller="memory_manager",
        )
        if not result_obj.success:
            logger.error("[ConversationSummarizer] 即時摘要 LLM 呼叫失敗：%s", result_obj.error)
            return Result(success=False, error=result_obj.error)

        summary_text = result_obj.data if isinstance(result_obj.data, str) else str(result_obj.data)

        embedding = await self._compute_embedding(summary_text)

        return Result(
            success=True,
            data={
                "summary": summary_text,
                "embedding": embedding,
            },
        )

    async def _compute_embedding(self, summary_text: str) -> Optional[list]:
        """產生摘要的 embedding 向量."""
        if not self.call_embedding_func:
            return None
        result = await self.call_embedding_func(config.EMBEDDING_MODEL_NAME, summary_text)
        embedding = result.data if result.success else None
        if embedding is None:
            log_action("memory_manager", "embedding", "DEGRADED",
                       "embedding 計算失敗", "embedding 計算失敗")
            logger.warning("[ConversationSummarizer] embedding 計算失敗")
        return embedding

    async def check_importance(self, summary: str) -> Result:
        """評估摘要的重要性.

        Returns:
            Result(data=float) 重要性分數 (0~1)
        """
        if not self.call_model_func:
            return Result(success=True, data=0.5)

        prompt = IMPORTANCE_PROMPT.format(SUMMARY=summary)
        messages = [{"role": "user", "content": prompt}]
        try:
            result_obj = await self.call_model_func(
                config.MEDIUM_MODEL_NAME,
                messages,
                config.SUMMARY_TEMPERATURE,
                config.SUMMARY_MAX_TOKENS,
                False,
                caller="memory_manager_importance",
            )
            if not result_obj.success:
                log_action("memory_manager", "importance_llm", "DEGRADED",
                           result_obj.error or "unknown", "重要性評估失敗，使用預設值")
                return Result(success=True, data=0.5)

            result = result_obj.data if isinstance(result_obj.data, str) else str(result_obj.data)
            match = re.search(r'(\d+\.\d+|\d+)', result)
            raw_score = float(match.group()) if match else 0.5
            clamped = max(0.0, min(1.0, raw_score))
            return Result(success=True, data=clamped)
        except Exception as e:
            logger.warning("[ConversationSummarizer] 重要性評估失敗：%s", e)
            return Result(success=True, data=0.5)

    async def batch_summarize(self, items: List[dict]) -> Result:
        """將 TempCache 的 top-k 項目合併為一份長期記憶摘要.

        Args:
            items: TempCache.get_top_k() 回傳的項目列表

        Returns:
            Result(data={"summary": str, "embedding": list | None}) 成功
            Result(success=False, error=str) 失敗
        """
        if not items or not self.call_model_func:
            return Result(success=False, error="empty items or no model func")

        combined = "\n---\n".join(item["summary"] for item in items)

        # 計算 embedding
        embedding = None
        if self.call_embedding_func:
            result = await self.call_embedding_func(config.EMBEDDING_MODEL_NAME, combined)
            embedding = result.data if result.success else None
            if embedding is None:
                log_action("memory_manager", "batch_embedding", "DEGRADED",
                           "batch embedding 計算失敗", "batch embedding 計算失敗")
                logger.warning("[ConversationSummarizer] batch embedding 計算失敗")

        prompt = BATCH_SUMMARY_PROMPT.format(num_items=len(items), summaries=combined)
        messages = [{"role": "user", "content": prompt}]
        try:
            result_obj = await self.call_model_func(
                config.MEDIUM_MODEL_NAME,
                messages,
                config.SUMMARY_TEMPERATURE,
                config.SUMMARY_MAX_TOKENS,
                False,
                caller="memory_manager_batch",
            )
            if result_obj.success:
                summary_text = result_obj.data if isinstance(result_obj.data, str) else str(result_obj.data)
                parsed = parse_first_json(summary_text)
                if isinstance(parsed, dict) and "intent" in parsed and "decisions" in parsed:
                    return Result(success=True, data={"summary": summary_text, "embedding": embedding})
                return Result(success=True, data={"summary": summary_text, "embedding": embedding})
            return Result(success=False, error=result_obj.error or "batch summarize failed")
        except Exception as e:
            logger.error("[ConversationSummarizer] 批量摘要 LLM 呼叫失敗：%s", e)
            return Result(success=False, error=str(e))
