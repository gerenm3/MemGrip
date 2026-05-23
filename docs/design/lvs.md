# LVS（Learning Value Score）設計

## 1. 概述

LVS 是 Learning Value Score 的簡稱，用於評估複雜任務的執行品質，並根據累計評分觸發 optimizer 自動優化 skill guide。

### 核心概念

- **Q 分**：單一任務的品質分數，越高表示問題越多
- **全域分數（G）**：所有任務 Q 分的累計值
- **觸發機制**：當 G ≥ 100 時，觸發 optimizer 自動優化 skill guide
- **重置機制**：觸發後 G *= 0.2（保留 20% 殘餘）

## 2. Q 分計算公式

Q 分由五個維度組成，各維度設有上限：

```python
Q = min(30, final_fail * 30)
  + min(20, failed_units * 8)
  + min(10, replan_count * 10)
  + min(6, review_fail * 3)
  + min(4, loop_hit * 4)

# 總分上限
Q = min(Q, 65)
```

### 分數權重分析

| 維度 | 變數 | 單單位數 | 上限 | 說明 |
|------|------|---------|------|------|
| 任務失敗 | final_fail | 30 分/次 | 30 分 | 任務層級失敗的權重最高 |
| 單元失敗 | failed_units | 8 分/個 | 20 分 | 子任務單元的失敗數量 |
| 重新規劃 | replan_count | 10 分/次 | 10 分 | 單元規劃重做的次數 |
| 審核失敗 | review_fail | 3 分/次 | 6 分 | LLM 審核通過的失敗次數 |
| 循環耗盡 | loop_hit | 4 分/個 | 4 分 | 達到 max_iterations(5) 的單元數 |

## 3. 變因定義

### final_fail
```
final_fail = 1 if task_record["final_status"] == "failed" else 0
```

### failed_units
```
failed_units = 所有 status == "FAILED" 的 unit 數量
```

### replan_count
```
replan_count = 所有 unit["replan_count"] 的總和
```

### review_fail
從 `trace.jsonl` 統計本次任務的審核失敗次數：
- 篩選 `session_id` 匹配的記錄
- 篩選 `caller == "executor_verify"` 的記錄
- 從 `messages` 中提取 `passed` 欄位
- 統計 `passed == false` 的次數

### loop_hit
```
loop_hit = 所有 total_loop_count >= max_iterations(5) 的 unit 數量
```

## 4. 全域分數與觸發機制

### 分數累積
```python
G += Q
```

### 觸發條件
```python
if G >= 100:
    trigger_optimizer()
    G *= 0.2  # 保留 20% 殘餘
```

### 設計理由

為什麼保留 20% 殘餘而非完全歸零？

- **連續問題的敏感性**：如果連續發生多次品質問題，保留殘餘可確保下一次問題能更快再次觸發 optimizer
- **避免過度觸發**：不會每次都觸發，讓 optimizer 專注處理真正有問題的任務

## 5. 持久化格式

### 檔案位置
```
skills/lvs_state.json
```

### JSON 結構
```json
{
  "global_score": 0.0,
  "last_optimizer_run": "2026-05-22T19:30:00+08:00"
}
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| global_score | float | 累計全域分數，初始值 0.0 |
| last_optimizer_run | string \| null | 最近一次 optimizer 執行的 ISO 時間戳，初始 null |

## 6. 模組設計

### skills/lvs.py

提供 LVS 核心功能：

| 函數 | 輸入 | 輸出 | 說明 |
|------|------|------|------|
| `calculate_q(task_record)` | task_record（dict） | q（float） | 計算單一任務的 Q 分 |
| `update_global_score(q)` | q（float） | global_score（float） | 更新並回傳全局分數 |
| `should_trigger()` | 無 | bool | 檢查是否觸發 optimizer |
| `reset_after_trigger()` | 無 | str \| None | 重置狀態，回傳執行時間 |
| `get_global_score()` | 無 | float | 取得當前 global_score（不修改） |

### calculate_q() 詳細流程

```
calculate_q(task_record):
    1. final_fail = 1 if task_record["final_status"] == "failed" else 0
    2. failed_units = count(unit["status"] == "FAILED" for unit in task_record["units"])
    3. replan_count = sum(unit["replan_count"] for unit in task_record["units"])
    4. review_fail = count_review_fails(task_record)      # 從 trace.jsonl 統計
    5. loop_hit = count(unit["total_loop_count"] >= 5 for unit in task_record["units"])
    6. q = min(30, final_fail*30) + min(20, failed_units*8) + min(10, replan_count*10) + min(6, review_fail*3) + min(4, loop_hit*4)
    7. return min(q, 65)
```

### update_global_score() 與 reset_after_trigger() 協同流程

```python
# 檢查觸發
if should_trigger():
    g = update_global_score(q)        # G += Q
    last_run = reset_after_trigger()   # G *= 0.2, 記錄時間
    trigger_optimizer()

else:
    g = update_global_score(q)        # 僅累積，不觸發
```

## 7. Orchestrator 整合

### 整合位置
`core/orchestrator.py` → `_handle_complex_intent()`

### 執行流程

```python
_handle_complex_intent():
    ...
    1. 執行 Units (executor.execute_units)
    2. 記錄任務 trace (log_task)
    3. 構建 task_record
        - session_id: 從 session 儲存
        - final_status: failed/success
        - units: [unit_id, status, replan_count, total_loop_count, ...]
    4. q = calculate_q(task_record)
    5. if should_trigger():
         - g = update_global_score(q)
         - reset_after_trigger()
         - create_task(run_optimizer(session_id, task_type))
         - log_task()  # 記錄本次任務問題
         - integrate() → 回傳 "⚠️ Q={q:.0f}，已觸發 optimizer"
    6. else:
         - update_global_score(q)
         - log_task()
         - integrate() → 正常回應
```

### 觸發優化時的回應

```
⚠️ 本任務品質不佳（Q=45），已觸發 optimizer 優化 skill guide。
[原本的整合回應內容]
```

## 8. 設計考量

### 為什麼 Q 分上限設為 65？

- 單一任務最多貢獻 65 分，確保需要多個問題任務才能觸發 optimizer
- 避免單一極端案例導致頻繁觸發

### 為什麼 failed_units 上限設為 20？

- 假設一個任務拆分為多個 unit，即使所有 unit 都失敗（例如 5 個），
  failed_units * 8 = 40，但上限 20 限制了這維度的影響力
- 促使 optimizer 關注更根本的規劃問題

### 為什麼 replan_count 上限設為 10？

- 高權重反映規劃不穩定性：每次 replan 表示 planner 的預測有誤
- 但上限 10 避免單一任務過度主導 Q 分

## 9. 預期行為

### 情境一：單一失敗任務
```
Q = 30 (final_fail) = 30
G = 30（未觸發，< 100）
```

### 情境二：多次小問題
```
任務 1: Q = 16 (failed_units=2) → G = 16
任務 2: Q = 16 (failed_units=2) → G = 32
任務 3: Q = 16 (failed_units=2) → G = 48
任務 4: Q = 16 (failed_units=2) → G = 64
任務 5: Q = 16 (failed_units=2) → G = 80
任務 6: Q = 16 (failed_units=2) → G = 96
任務 7: Q = 16 (failed_units=2) → G = 112 → 觸發！G *= 0.2 = 22.4
```

### 情境三：嚴重失敗任務
```
Q = 30 (final_fail) + 20 (failed_units=3) + 10 (replan_count=1) + 6 (review_fail=2) + 4 (loop_hit=1) = 70
# 但 min(70, 65) = 65
G = 65（未觸發）

後續再有問題任務即可觸發
```

## 10. 檔案清單

| 檔案 | 狀態 | 說明 |
|------|------|------|
| `skills/lvs.py` | 新增 | LVS 核心模組 |
| `core/orchestrator.py` | 修改 | 整合 LVS 評估流程 |
| `skills/lvs_state.json` | 新增（執行時） | 持久化狀態 |
| `docs/design/lvs.md` | 新增 | 本文檔 |

## 11. 日誌記錄

| 層級 | 時機 | 格式 |
|------|------|------|
| `info` | 觸發 optimizer | `[LVS] 觸發 optimizer (G=112.5, Q=45, last_run=2026-05-22T19:30:00+08:00)` |
| `debug` | 未觸發 | `[LVS] 未觸發 optimizer (G=80.0, Q=22)` |
| `error` | optimizer 呼叫失敗 | `[LVS] optimizer 呼叫失敗：<error>` |

## 12. 未來擴展方向

1. **分數衰退機制**：長時間未觸發 optimizer 時，自動降低閾值
2. **維度權重調整**：根據歷史數據動態調整各維度的權重
3. **任務類型加權**：不同 task_type 使用不同的觸發閾值
4. **監控儀表板**：提供 LVS 分數的歷史趨勢圖
