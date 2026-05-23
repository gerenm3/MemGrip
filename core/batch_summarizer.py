"""Batch Summarizer — Temp Cache 批量處理"""

import config
from typing import Any, List


class BatchSummarizer:
    """將 Temp Cache 中的多個摘要合併為結構化記憶"""

    def __init__(self, call_model_func: Any) -> None:
        self.call_model_func = call_model_func

    async def flush(self, temp_cache: Any) -> None:
        """從 temp_cache 取出 top_k 項目，進行資訊萃取，然後從 Cache 移除

        Args:
            temp_cache: TempCache 實例，用於取出項目和移除已處理項目
        """
        items = temp_cache.get_top_k(config.TEMP_CACHE_TOP_K)
        if not items:
            return

        # 合併摘要
        combined = "\n---\n".join(item["summary"] for item in items)

        prompt = f"""你是一個資訊萃取器。以下是 {len(items)} 段對話摘要，它們都來自於同一次使用者互動的不同階段。
請將它們合併為一份結構化的長期記憶。

[SUMMARIES]
{combined}
[/SUMMARIES]

僅輸出 JSON：
{{
  "intent": "..",
  "decisions": [{{"decision": "..", "reason": ".."}}],
  "pending": [".."],
  "preferences": [".."]
}}"""

        messages = [{"role": "user", "content": prompt}]
        try:
            result, _ = await self.call_model_func(
                config.MEDIUM_MODEL_NAME,
                messages,
                config.SUMMARY_TEMPERATURE,
                config.SUMMARY_MAX_TOKENS,
                False,
                caller="batch_summarizer",
            )

            if result:
                # 萃取成功：新的 summary 重新進入分流邏輯
                # （由呼叫端決定如何處理 result）
                pass

        except Exception as e:
            # 萃取失敗：項目保留在 Cache，等待下一次 batch
            pass
        finally:
            # 無論成敗，都從 Cache 移除該項目
            for item in items:
                temp_cache.remove(item["id"])

    async def summarize_batch(self, items: List[dict]) -> str | None:
        """合併並萃取 batch 中的摘要

        Returns:
            萃取後的 JSON 字串，失敗則回傳 None
        """
        combined = "\n---\n".join(item["summary"] for item in items)

        prompt = f"""你是一個資訊萃取器。以下是 {len(items)} 段對話摘要，它們都來自於同一次使用者互動的不同階段。
請將它們合併為一份結構化的長期記憶。

[SUMMARIES]
{combined}
[/SUMMARIES]

僅輸出 JSON：
{{
  "intent": "..",
  "decisions": [{{"decision": "..", "reason": ".."}}],
  "pending": [".."],
  "preferences": [".."]
}}"""

        messages = [{"role": "user", "content": prompt}]
        result, _ = await self.call_model_func(
            config.MEDIUM_MODEL_NAME,
            messages,
            config.SUMMARY_TEMPERATURE,
            config.SUMMARY_MAX_TOKENS,
            False,
            caller="batch_summarizer",
        )
        return result
