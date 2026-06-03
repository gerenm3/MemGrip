"""v2 summary — 對話摘要與 TempCache.

依據 §3.13 (Memory Layer) + §5.4 (摘要分流) 定義：
- ConversationSummary：對話摘要狀態
- TempCache：具衰減優先級的暫存記憶體
- 指數衰減：confidence × exp(-λ × age_hours)（§3.13 保留）
"""

import math
import time
import uuid
from typing import Dict, List

import config
from memory.buffer import estimate_tokens


class ConversationSummary:
    """對話摘要長期儲存。"""

    def __init__(self) -> None:
        self.summary: str = ""

    def set_summary(self, text: str) -> None:
        self.summary = text

    def get_summary(self) -> str:
        return self.summary


class TempCache:
    """Uncertain memory staging area with decay-based priority queue"""

    def __init__(self) -> None:
        self.items: Dict[str, Dict] = {}  # id -> item

    def add(self, raw_chunk: List, summary: str,
            similarity_score: float, importance_score: float) -> str:
        """加入新項目，回傳 item id"""
        confidence = (similarity_score + importance_score) / 2

        item = {
            "id": str(uuid.uuid4()),
            "raw_chunk": raw_chunk,
            "summary": summary,
            "confidence": confidence,
            "similarity_score": similarity_score,
            "importance_score": importance_score,
            "timestamp": time.time(),
            "token_count": estimate_tokens(summary),
            "importance": importance_score,
        }

        self.items[item["id"]] = item
        self._enforce_capacity()
        return item["id"]

    def _enforce_capacity(self) -> None:
        """移除 effective_importance 最低的項目直到低於上限"""
        while (len(self.items) > config.TEMP_CACHE_MAX_ITEMS or
               self.total_tokens() > config.TEMP_CACHE_MAX_TOKENS):
            if not self.items:
                break
            worst_id = min(
                self.items,
                key=lambda oid: self._effective_importance(self.items[oid])
            )
            if self._effective_importance(self.items[worst_id]) >= config.TEMP_CACHE_EVICTION_THRESHOLD:
                break
            del self.items[worst_id]

    def _effective_importance(self, item: Dict) -> float:
        age_hours = max(0, (time.time() - item["timestamp"]) / 3600)
        return item["confidence"] * math.exp(-config.TEMP_CACHE_DECAY_LAMBDA * age_hours)

    def get_top_k(self, k: int) -> List[Dict]:
        """取前 k 個最高 effective_importance 的項目（含 decay 更新）"""
        sorted_items = sorted(
            self.items.values(),
            key=lambda item: self._effective_importance(item),
            reverse=True
        )
        return [item for item in sorted_items[:k]]

    def remove(self, item_id: str) -> bool:
        if item_id in self.items:
            del self.items[item_id]
            return True
        return False

    def total_tokens(self) -> int:
        return sum(item["token_count"] for item in self.items.values())

    def count(self) -> int:
        return len(self.items)

    def clear(self) -> None:
        self.items.clear()
