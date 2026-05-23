class ConversationSummary:
    def __init__(self) -> None:
        self.summary: str = ""
        self.cached_flushed: list[dict] = []

    def set_summary(self, text: str) -> None:
        self.summary = text

    def get_summary(self) -> str:
        return self.summary

    def add_cache(self, flushed: list) -> None:
        self.cached_flushed.extend(flushed)


import json
import uuid
import time
import math
import config


class TempCache:
    """Uncertain memory staging area with decay-based priority queue"""

    def __init__(self) -> None:
        self.items: dict[str, dict] = {}  # id -> item

    def add(self, raw_chunk: list, summary: str,
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
            "token_count": self._estimate_tokens(summary),
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

    def _effective_importance(self, item: dict) -> float:
        age_hours = (time.time() - item["timestamp"]) / 3600
        return item["confidence"] * math.exp(-config.TEMP_CACHE_DECAY_LAMBDA * age_hours)

    def get_top_k(self, k: int) -> list[dict]:
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

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 4
