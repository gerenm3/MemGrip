# Temp Cache — Uncertain Memory Staging

## 1. 設計概念

Temp Cache 是「不確定記憶的臨時暫存區」，不是垃圾桶。

當摘要的置信度介於「明確值得儲存」與「明確不值得儲存」之間時，
進入 Temp Cache 等待更多證據（時間 decay、後續引用、批量處理重估）。

### 核心原則

- **進入條件基於 confidence score，不是單純 similarity fail**
- 進入 Temp Cache 的資料仍會持續 decay，不會永久停留
- 高置信度 → 直接進向量庫；低置信度 → 直接丟棄

---

## 2. Confidence Score

### 計算方式

```
# similarity_score 原始範圍 0.5~1.5（來自 compare() 的 normalized cosine），正規化到 0~1
normalized_similarity = (similarity_score - 0.5) / 1.0

# importance_score 需 clamp 到 0~1
importance_score = max(0.0, min(1.0, raw_score))

# confidence 為兩者平均
confidence = (normalized_similarity + importance_score) / 2
```

| 分數 | 範圍 | 行為 |
|------|------|------|
| 高置信 | > TEMP_CACHE_HIGH_CONFIDENCE (0.7) | 存入向量資料庫 |
| 低置信 | < TEMP_CACHE_LOW_CONFIDENCE (0.3) | 直接丟棄 |
| 待定 | [0.3, 0.7] | 進入 Temp Cache |

### 現有常數對應

| 現有常數 | 新常數 | 說明 |
|---------|--------|------|
| `SIMILARITY_THRESHOLD = 0.6` | 改為 `TEMP_CACHE_LOW_CONFIDENCE = 0.3` | 下限閾值 |
| `IMPORTANCE_THRESHOLD = 0.5` | 改為 `TEMP_CACHE_HIGH_CONFIDENCE = 0.7` | 上限閾值 |

---

## 3. Temp Cache 資料結構

### Item Schema

每個 temp cache item 的 JSON 結構：

```json
{
  "id": "uuid4",
  "raw_chunk": [
    {"role": "user", "content": "你好，幫我建立一個 Python 專案"},
    {"role": "assistant", "content": "好的，我會為您建立..."}
  ],
  "summary": "用戶想建立 Python 專案，助理表示同意",
  "confidence": 0.42,
  "similarity_score": 0.35,
  "importance_score": 0.49,
  "timestamp": "2026-05-21T14:00:00Z",
  "token_count": 150,
  "importance": 0.42
}
```

### 欄位說明

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | `str` | UUID4 唯一識別碼 |
| `raw_chunk` | `list[dict]` | 原始對話片段（從 buffer flush 的原始資料） |
| `summary` | `str` | 9B 模型生成的摘要 |
| `confidence` | `float` | `(similarity_score + importance_score) / 2` |
| `similarity_score` | `float` | 與向量庫現有記錄的相似度分數 |
| `importance_score` | `float` | LLM 評估的重要性分數 |
| `timestamp` | `str` | ISO 8601 時間戳記 |
| `token_count` | `int` | 估算的 token 數量 |
| `importance` | `float` | 有效重要性，隨時間 decay（初始 = importance_score） |

---

## 4. Priority Queue — 有效重要性排序

### 计算公式

```
effective_importance = confidence * e^(-lambda * age_hours)
```

| 參數 | 值 | 說明 |
|------|------|------|
| `TEMP_CACHE_DECAY_LAMBDA` | `0.01` | 衰減係數 |

### 排序規則

- 按 `effective_importance` **降序**排列
- 每當執行 `get_top_k()` 時，先呼叫 `update_decay()` 更新所有項目 age
- 每 3600 秒（1 小時）的 age 增加 1

### 自動清理

當 `effective_importance < TEMP_CACHE_EVICTION_THRESHOLD (0.05)` 時，
該項目視為已完全衰減，不進入取樣直接移除。

---

## 5. 容量控制

| 參數 | 值 | 說明 |
|------|------|------|
| `TEMP_CACHE_MAX_TOKENS` | `50000` | Token 容量上限 |
| `TEMP_CACHE_MAX_ITEMS` | `100` | 項目數量上限 |

### 超限處理

- 當累積 token 數 > `TEMP_CACHE_MAX_TOKENS` 時：
  - 移除 `effective_importance` 最低的項目
  - 重複直到低於上限
- 當項目數 > `TEMP_CACHE_MAX_ITEMS` 時：
  - 移除 `effective_importance` 最低的項目
  - 重複直到低於上限

---

## 6. 觸發條件

### 常規觸發（閒置定時器）

| 參數 | 值 | 說明 |
|------|------|------|
| `TEMP_CACHE_IDLE_SECONDS` | `900` | 閒置 15 分鐘觸發 batch summary |

- 紀錄 `last_batch_time`（最後一次 batch 的時間）
- 當 `current_time - last_batch_time >= TEMP_CACHE_IDLE_SECONDS` 時觸發
- 觸發後更新 `last_batch_time`

### 強制觸發（累積量閾值）

| 參數 | 值 | 說明 |
|------|------|------|
| `TEMP_CACHE_FORCE_TOKENS` | `8000` | 強制觸發的 token 閾值 |

- 當 Temp Cache 累積 token 數 >= `TEMP_CACHE_FORCE_TOKENS` 時強制觸發
- 防止大量資料積壓

### 觸發優先級

```
強制觸發 > 常規觸發
（兩者同時滿足時，以強制觸發為主，但結果相同：執行 batch）
```

---

## 7. 批量處理

### 取樣策略

- 每次取 `TEMP_CACHE_TOP_K (10)` 個 **最高 effective_importance** 的項目
- 若 Cache 內項目少於 10 個，全部取出

### 合併與 Prompt

- 將取出的項目 summary 合併為一個長的對話摘要
- 發送給大模型（或同一個 MEDIUM 模型）執行 **資訊萃取**
- Prompt 設計重點：是「從已有摘要中提取結構化資訊」，不是「重新摘要」

### Prompt 範例

```
你是一個資訊萃取器。以下是 N 段對話摘要，它們都來自於同一次使用者互動的不同階段。
請將它們合併為一份結構化的長期記憶，提取以下資訊：
- 用戶的明確意圖與目標
- 重要的決策點與理由
- 待處理事項與後續步驟
- 用戶偏好與習慣

[SUMMARIES]
{合併的 N 段摘要}
[/SUMMARIES]

僅輸出 JSON，格式：
{
  "intent": "..."
  "decisions": [{"decision": "...", "reason": "..."}],
  "pending": ["..."],
  "preferences": ["..."]
}
```

### 處理完成後

- 萃取成功的記憶 → 產生新的 embedding → 進入常規分流（高→向量庫，中→回 Cache，低→丟棄）
- 萃取失敗 → 項目保留在 Cache，等待下一次 batch
- 無論成敗，都從 Cache 移除該項目（成功是因為已處理，失敗是因為已重試）

---

## 8. 修改清單

### 8.1 `config.py` — 新增常數

```python
# --- Temp Cache ---
TEMP_CACHE_PATH = "./temp_cache"                    # 已存在（第 73 行）
TEMP_CACHE_HIGH_CONFIDENCE = 0.7                    # 新
TEMP_CACHE_LOW_CONFIDENCE = 0.3                     # 新
TEMP_CACHE_DECAY_LAMBDA = 0.01                      # 新
TEMP_CACHE_MAX_TOKENS = 50000                       # 新
TEMP_CACHE_MAX_ITEMS = 100                          # 新
TEMP_CACHE_IDLE_SECONDS = 900                       # 新
TEMP_CACHE_FORCE_TOKENS = 8000                      # 新
TEMP_CACHE_TOP_K = 10                               # 新
TEMP_CACHE_EVICTION_THRESHOLD = 0.05               # 新
```

### 8.2 `memory/summary.py` — 新增 Temp Cache 模組

```python
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
        self.update_decay()
        sorted_items = sorted(
            self.items.values(),
            key=lambda item: self._effective_importance(item),
            reverse=True
        )
        return [item for item in sorted_items[:k]]

    def update_decay(self) -> None:
        """更新所有項目的 effective_importance（lazy evaluation，不需要寫回）"""
        pass  # 在 _effective_importance 中動態計算

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
```

### 8.3 `core/summarizer.py` — 修改分流邏輯

**當前邏輯（第 43–52 行）：**

```python
if self.vector.compare(embedded) > config.SIMILARITY_THRESHOLD:
    return  # similarity 太高 → 跳過（去重）

score = await self._check_importance(summary_text)
if not score or score < config.IMPORTANCE_THRESHOLD:
    return  # importance 太低 → 跳過

self.vector.add(summary_text, flushed, embedded)  # 直接存入
```

**新邏輯：**

```python
similarity_score = self.vector.compare(embedded)
importance_score = await self._check_importance(summary_text)

if not importance_score:
    importance_score = 0.0

confidence = (similarity_score + importance_score) / 2

if confidence > config.TEMP_CACHE_HIGH_CONFIDENCE:
    # 高置信 → 存入向量庫
    self.vector.add(summary_text, flushed, embedded)

elif confidence < config.TEMP_CACHE_LOW_CONFIDENCE:
    # 低置信 → 丟棄
    pass

else:
    # 中間區 → 進入 Temp Cache
    self.temp_cache.add(
        raw_chunk=flushed,
        summary=summary_text,
        similarity_score=similarity_score,
        importance_score=importance_score,
    )
```

**需要修改的地方：**

1. `Summarizer.__init__` 加入 `temp_cache: TempCache` 參數
2. `bootstrap.py` 組裝時注入 `temp_cache`
3. `summarize()` 方法替換第 43–52 行邏輯

### 8.4 `bootstrap.py` — 組裝時注入 TempCache

```python
def build_orchestrator() -> Orchestrator:
    # ... 現有 code ...
    
    temp_cache = TempCache()
    summarizer = Summarizer(call_model, call_embedding, summary, vector, temp_cache)
    
    return Orchestrator(
        # ... 現有 code ...
        summarizer=summarizer,
        temp_cache=temp_cache,
    )
```

### 8.5 `core/orchestrator.py` — 加入閒置觸發邏輯

在 `Orchestrator` 中加入：

```python
import time

class Orchestrator:
    def __init__(self, ..., temp_cache: TempCache, **kwargs) -> None:
        # ... 現有 code ...
        self.temp_cache = temp_cache
        self.last_batch_time = 0.0

    def _check_batch_trigger(self) -> bool:
        """檢查是否應該觸發 batch summary"""
        if not self.temp_cache.items:
            return False
        
        idle_seconds = time.time() - self.last_batch_time
        force_trigger = self.temp_cache.total_tokens() >= config.TEMP_CACHE_FORCE_TOKENS
        
        if idle_seconds >= config.TEMP_CACHE_IDLE_SECONDS or force_trigger:
            return True
        return False

    async def _trigger_batch_summary(self) -> None:
        """執行 batch summary 處理"""
        items = self.temp_cache.get_top_k(config.TEMP_CACHE_TOP_K)
        if not items:
            return
        
        # 合併摘要
        combined_summaries = "\n---\n".join(item["summary"] for item in items)
        
        # 呼叫 LLM 進行資訊萃取
        # ... (細節由 batch_summarizer.py 處理) ...
        
        # 處理完成後從 Cache 移除
        for item in items:
            self.temp_cache.remove(item["id"])
        
        self.last_batch_time = time.time()
```

### 8.6 新建 `core/batch_summarizer.py` — 批量處理邏輯

```python
"""Batch Summarizer — Temp Cache 批量處理"""

import config
from typing import Any, List


class BatchSummarizer:
    """將 Temp Cache 中的多個摘要合併為結構化記憶"""

    def __init__(self, call_model_func: Any) -> None:
        self.call_model_func = call_model_func

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
  "intent": "...",
  "decisions": [{{"decision": "...", "reason": "..."}}],
  "pending": ["..."],
  "preferences": ["..."]
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
```

---

## 9. 現有程式碼影響範圍

### 不受影響

| 模組 | 原因 |
|------|------|
| `memory/vector.py` | `compare()` 和 `add()` API 不變 |
| `memory/buffer.py` | 不接觸 Temp Cache |
| `clients/` | 不接觸 |
| `core/executor.py` | 不接觸 |
| `core/router.py` | 不接觸 |

### 需要修改

| 檔案 | 修改內容 |
|------|---------|
| `config.py` | 新增 8 個 TEMP_CACHE_* 常數 |
| `memory/summary.py` | 新增 `TempCache` class |
| `core/summarizer.py` | 修改 `__init__` 和 `summarize()` 分流邏輯 |
| `bootstrap.py` | 組裝時注入 `TempCache` |
| `core/orchestrator.py` | 加入 `temp_cache` 參數與 batch 觸發邏輯 |
| `core/batch_summarizer.py` | **新建**，批量處理模組 |

---

## 10. Flow 圖

```
[flushed turns]
       │
       ▼
[LLM generate summary]
       │
       ▼
[generate embedding]
       │
       ▼
[similarity_score = vector.compare(embedded)]
       │
       ▼
[importance_score = LLM evaluate]
       │
       ▼
[confidence = (similarity + importance) / 2]
       │
       ├── > 0.7 (HIGH) ──────► [vector.add()] → 存入向量庫
       │
       ├── [0.3, 0.7] (MIDDLE) ──► [temp_cache.add()] → 進入 Temp Cache
       │                               │
       │                               ├── idle >= 900s  ──► batch trigger
       │                               ├── total_tokens >= 8000  ──► force trigger
       │                               │
       │                               ▼
       │                         [get_top_k(10)]
       │                               │
       │                               ▼
       │                         [LLM 資訊萃取]
       │                               │
       │                               ▼
       │                    [新的 summary → 重新進入分流]
       │
       └── < 0.3 (LOW) ──────► [discard] → 丟棄
```

---

## 11. 與現有系統的互動

### 現有 `SIMILARITY_THRESHOLD = 0.6` 的變化

- **移除**：`SIMILARITY_THRESHOLD` 不再單獨作為判斷依據
- **保留**：`SIMILARITY_THRESHOLD` 常數可移除或改為備份（若其他模組仍有使用，需先確認）

### 現有 `IMPORTANCE_THRESHOLD = 0.5` 的變化

- **移除**：`IMPORTANCE_THRESHOLD` 不再單獨作為判斷依據
- **新角色**：僅供歷史參考，被 `TEMP_CACHE_HIGH_CONFIDENCE` 和 `TEMP_CACHE_LOW_CONFIDENCE` 取代

---

## 12. 實作順序建議

1. **config.py** — 新增常數（無相依性）
2. **memory/summary.py** — 新增 `TempCache` class（無相依性）
3. **core/batch_summarizer.py** — 新建（僅相依 `config` 和 `call_model_func`）
4. **core/summarizer.py** — 修改分流邏輯（相依 TempCache）
5. **bootstrap.py** — 注入 `TempCache`（相依 TempCache + Summarizer）
6. **core/orchestrator.py** — 加入 batch 觸發（相依 TempCache + BatchSummarizer）

---

## 13. 測試建議

| 測試項目 | 預期行為 |
|---------|---------|
| `TempCache.add()` 超過 MAX_ITEMS | 自動移除 lowest effective_importance |
| `TempCache.add()` 超過 MAX_TOKENS | 自動移除 lowest effective_importance |
| `get_top_k()` 回傳正確排序 | 按 effective_importance 降序 |
| `decay` 隨時間降低 effective_importance | 1 小時後約降 1% |
| confidence > 0.7 直接進向量庫 | 不進入 Temp Cache |
| confidence < 0.3 直接丟棄 | 不進入 Temp Cache |
| idle trigger 觸發 batch | idle >= 900s 時 `check_batch_trigger()` 回傳 True |
| force trigger 觸發 batch | total_tokens >= 8000 時 `check_batch_trigger()` 回傳 True |
