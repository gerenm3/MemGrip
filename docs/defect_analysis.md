# MemGrip 潛在缺陷分析報告

本文檔從五個角度評估 MemGrip 系統的潛在缺陷，依嚴重程度由高到低排序。

---

## 嚴重程度分級說明

| 等級 | 定義 |
|------|------|
| **C1 (Critical)** | 系統崩潰或資料永久損壞 |
| **C2 (High)**   | 功能異常或安全風險，可復現 |
| **C3 (Medium)**  | 效能問題或使用者體驗降低 |
| **C4 (Low)**     | 設計瑕疵但不影響運作 |

---

## 一、單點故障（Single Point of Failure）

### D1. C1 — `new_session()` 只在 bootstrap.py 初始化一次

**位置**：`bootstrap.py:24`

**問題描述**：
`new_session()` 只在系統啟動時呼叫一次。每次互動的 `orchestrator.run()` 第 58 行也呼叫 `new_session()`，但這會覆寫前一次 session 的 tracer 狀態，導致 **trace.jsonl 的 session_id 在所有輪次間共享同一個 session_id**，無法區分不同對話回合的記錄。

**影響**：
- 優化器（Optimizer）無法透過 session_id 精確篩選特定對話的 trace
- `TraceReader.build_execution_record()` 會將所有回合的 trace 混為一筆記錄

**觸發條件**：每次互動式模式下，連續兩次以上輸入

**修複方向**：每次 `run()` 循環應產生獨立 session_id，或每次對話回合應有獨立 trace context

---

### D2. C1 — `asyncio.create_task()` 的 fire-and-forget 摘要任務可能被 GC 收集

**位置**：`orchestrator.py:193`

```python
def _summarize_if_needed(self) -> None:
    flushed = self.buffer.storage()
    if flushed and self.summarizer:
        asyncio.create_task(self.summarizer.summarize(flushed))
```

**問題描述**：
`asyncio.create_task()` 回傳的 Task 物件只有被參考時才會執行。若沒有將 task 物件儲存在某處（如 `self._tasks`），當 `_summarize_if_needed()` 回傳後，task 可能被 Python GC 收集導致摘要不執行。

**影響**：
- Memory 容量達到上限時， flushed 對話不會被摘要
- 長期使用下 memory.buffer 無限增長
- 向量資料庫不會有新記錄

**觸發條件**：buffer 超過容量上限

**修複方向**：
```python
self._summarize_tasks = getattr(self, '_summarize_tasks', [])
task = asyncio.create_task(self.summarizer.summarize(flushed))
self._summarize_tasks.append(task)
task.add_done_callback(self._summarize_tasks.remove)
```

---

### D3. C2 — Ollama LLM 服務不可用時系統無 graceful degradation

**位置**：`clients/model_client.py`（所有 LLM 呼叫）

**問題描述**：
所有模組（Router、Clarifier、Planner、Executor、Responder、Summarizer）都依賴 `call_model_func`。當 Ollama 服務關閉或網路中斷時：

1. Router 無法判斷 intent → 使用者輸入無回應
2. Executor 無法規劃/執行 → 整個 complex 任務失敗
3. Summarizer 無法壓縮記憶 → 記憶體無限增長

目前僅在 `orchestrator.run()` 的 `_init_tools()` 有 `try/except`（第 44-47 行），但 **LLM 呼叫本身沒有任何全域錯誤處理**。

**影響**：
- 系統完全無法運作
- 使用者看到空白或 traceback

**觸發條件**：Ollama 服務停止、API key 失效、網路中斷

**修複方向**：
- 在 `_dispatch_by_intent()` 加入 health check
- 提供 local fallback 模式（如規則式回應）

---

### D4. C2 — MCP Server 初始化失敗無 recovery

**位置**：`tool_manager.py:_init_tools()`

**問題描述**：
`_init_tools()` 如果其中一個 MCP server 連線失敗，可能導致整個 `server_schemas` 為空。系統雖然在 orchestrator 有檢查 `has_tools` 並提示使用者，但沒有 partial fallback（例如部分 server 成功時仍可運作）。

**影響**：單一 MCP server 故障可能導致所有工具不可用

**修複方向**：改為 per-server error handling，成功的 server 照常運作

---

## 二、資料一致性（Data Consistency）

### D5. C2 — trace.jsonl 與 task_trace.jsonl 的 session_id 不同步

**位置**：`core/tracer.py`

**問題描述**：
- `trace.jsonl` 的 `session_id` 來自 `new_session()`（每次 run() 呼叫都會更新全局 `current_session_id`）
- `task_trace.jsonl` 的 `session_id` 也在 `log_task()` 中使用相同的 `current_session_id`

但在 `orchestrator.py:58`，`new_session()` 在每次使用者輸入前呼叫。如果：
1. 使用者輸入 A → `new_session()` 產生 session_id = S1
2. `_dispatch_by_intent("complex", ...)` 執行 → `log_task(task_type, ..., session_id=S1)`
3. 此時 L1/L2/L3 各階段也寫入 trace.jsonl，但 `call_model_func()` 的 `caller` 參數可能使用舊的 session context

**實際影響**：trace 記錄和 task trace 的 session_id 可能不一致，導致 Optimizer 無法正確關聯

**修複方向**：使用 transactional context（如 `contextvar`）確保同一次任務的所有寫入使用同一 session_id

---

### D6. C3 — Summarizer 的 `addCache` → `setSummary` 原子性不足

**位置**：`summarizer.py:27-34`

```python
async def summarize(self, flushed: List[dict]) -> None:
    self.summary.add_cache(flushed)  # 第 27 行
    ...
    summary_text, _ = await self._call_llm(...)  # 第 33 行
    self.summary.set_summary(summary_text)  # 第 34 行
```

**問題描述**：
如果第 33 行 LLM 呼叫失敗（exception），`add_cache(flushed)` 已經將資料從 buffer 移除，但 `set_summary` 不會被執行。導致：
- buffer 中的對話紀錄已消失
- summary 未更新
- 資料永久丟失

**影響**：對話歷史丟失且無法復原

**修複方向**：先呼叫 LLM 取得 summary，成功後再 `add_cache`

---

### D7. C3 — Skill Guide 的 concurrent write 風險

**位置**：`skills/skill_manager.py`

**問題描述**：
`apply_update()` 同時寫入 `current.json` 和 `history/` 目錄。如果多輪對話同時觸發 optimizer（例如 user 連續輸入 complex 任務），可能產生：
- `current.json` 的 race condition
- history 檔案名稱衝突

**修複方向**：加入 file lock 或寫入隊列

---

## 三、錯誤處理（Error Handling）

### D8. C2 — Executor 的 Agentic Loop 無限循環風險

**位置**：`executor.py:386-441`

```python
async def _run_agentic_loop(self, step: Step, conversation: list, unit_id: str, step_id: str) -> dict:
    ...
    max_iterations = 20
    for _ in range(max_iterations):
        ...
        if tool_calls:
            ...
            conversation.append(assistant_msg)
            conversation.extend(tool_result_msgs)
            continue
        break
```

**問題描述**：
雖然有 `max_iterations = 20`，但：
1. 每次 iteration 都會呼叫 LLM（昂貴）
2. LLM 不斷回傳 tool_calls（如 read_file）→ 最多執行 20 次 API 呼叫
3. 沒有 total cost 或 total time budget 限制
4. 每個 Step 獨立的 20 次 iteration → 一個 Unit 可能有多个 Steps，每個都有 20 次

**實際影響**：一個 Unit 的 Agentic Loop 可能觸發 20 × N 次 LLM 呼叫（N = Steps 數量），成本不可控

**修複方向**：
- 加入 total token budget
- 加入 max time budget
- 減少默認 max_iterations（如 5-10）

---

### D9. C2 — `_is_error_result` 的錯誤判斷不精確

**位置**：`executor.py:461-467`

```python
@staticmethod
def _is_error_result(result: str) -> bool:
    if not result:
        return True
    result_lower = result.lower()
    error_keywords = ["access denied", "permission denied", "file not found", "error:", "traceback", "denied"]
    return any(kw in result_lower for kw in error_keywords)
```

**問題描述**：
1. `error:` 會誤判正常包含 "error:" 字串的回傳值（例如 JSON 中的某個欄位值）
2. `traceback` 只檢測 Python traceback，不涵蓋其他錯誤格式
3. 沒有處理 HTTP 500、timeout 等常見錯誤
4. 工具呼叫錯誤不會讓 loop 中斷，只是不加入 `successful_tool_results`

**影響**：錯誤的工具結果仍被当作成功結果使用，導致下游 step 拿到錯誤數據

**修複方向**：更精確的錯誤檢測（HTTP status code、JSON error format）

---

### D10. C3 — Clarifier 的 JSON parsing 失敗無 fallback

**位置**：`core/clarifier.py`（`_parse_json_response`）

**問題描述**：
如果 LLM 回傳的 JSON 格式無效（非合法 JSON），`_parse_json_response` 可能回傳空字典或不完整結果。系統沒有對不完整結果的驗證（如 goal 是否為空字串）。

**影響**： downstream Planner 收到空 goal → 產生空 Unit → 使用者得到「未產生任何執行單元」

**修複方向**：加入 JSON 結構驗證 + retry 機制

---

### D11. C3 — Router pattern match 失敗無 fallback

**位置**：`core/router.py`

**問題描述**：
如果 patterns.json 不存在或格式無效，regex 比對會失敗。雖然程式有 `except` 但可能直接回傳預設值，導致所有 intent 被分類為 `simple`。

**修複方向**：patterns.json 應有 default 值並記錄 warning

---

## 四、效能瓶頸（Performance Bottlenecks）

### D12. C3 — 每次使用者輸入都呼叫 `new_session()` 重設 tracer

**位置**：`orchestrator.py:58`

```python
while True:
    user_input = self._get_user_input()
    ...
    new_session()  # 每次循環都重設
```

**問題描述**：
每輪對話都呼叫 `new_session()` 重設 tracer session，導致：
- trace.jsonl 的新筆記錄覆蓋了前一個 session 的 context
- 每次 `log_model_call()` 的 `unit_id`/`step_id` 無法關聯到正確的任務階層
- task_trace.jsonl 的 `session_id` 也隨之失效

**影響**：追蹤數據無法反映真實的任務階層關係，Optimizer 無法使用

**修複方向**：`new_session()` 只在首次啟動時呼叫，或改用 nested context

---

### D13. C3 — Retriever 的 RAG 搜尋在每次 need_rag=True 時執行

**位置**：`orchestrator.py:66`

```python
rag_content = await self.retriever.retrieve(user_input) if need_rag else ""
```

**問題描述**：
- 每次輸入都執行 vector 搜尋（即使相似度高）
- `Summarizer` 在第 38 行做相似度檢查，但 `Retriever` 本身沒有 cache 機制
- 向量資料庫隨著時間增長，搜尋延遲線性增加

**修複方向**：
- Retriever 加入 result cache（TTL 機制）
- 向量資料庫加入索引優化

---

### D14. C3 — Executor 的 re-plan 不帶入 upstream outputs 的上下文

**位置**：`executor.py:212-214`

```python
successful_steps = step_store.get_successful_steps()
new_steps = await self.planner.plan_unit(unit, tools_list, successful_steps)
```

**問題描述**：
Re-plan 時只傳入 `successful_steps`，但沒有包含：
1. 失敗 step 的詳細錯誤資訊
2. 完整的 conversation history
3. 其他成功 unit 的輸出

**影響**：LLM 無法從失敗中學習，可能產生同樣的規劃錯誤

**修複方向**：re-plan prompt 應包含失敗原因分析

---

### D15. C4 — StepStore / UnitStore 的記憶體儲存無上限

**位置**：`core/storage.py`

**問題描述**：
StepStore 和 UnitStore 使用記憶體 dict 儲存所有 Step/Unit 的結果。對於複雜任務（100+ units，每 unit 10+ steps）：
- 記憶體使用量大
- 無法持久化，系統重啟後全部遺失

**修複方向**：加入 storage backend（SQLite 或文件系統）

---

## 五、設計債（Design Debt）

### D16. C2 — Optimizer 的 `verify()` 驗證邏輯與實際更新邏輯脫節

**位置**：`skills/optimizer.py`

**問題描述**：
Optimizer 的 verify 步驟驗證的是「更新後的 skill 是否能解決問題」，但驗證方式可能是基於 heuristic（規則檢查），而非真正執行 LLM 評估。這意味著：
- 驗證結果（passed/failed）可能不準確
- 重試機制（最多 3 次）可能無限循環（如果驗證邏輯本身有 bug）

**實際影響**：skill_guide 可能被錯誤更新，導致未來任務品質下降

**修複方向**：verify 應使用 LLM-as-judge 而非 heuristic

---

### D17. C3 — Responder.integrate() 的結果依賴 LLM 的品質

**位置**：`core/responder.py`

**問題描述**：
`integrate()` 將所有 unit 的結果丟給 LLM 產生最終回覆。如果：
- 某些 unit 失敗（output 為空）
- unit output 超過 context window
- LLM 在整合時忽略某些 unit

**影響**：最終回覆可能不完整或遺漏關鍵資訊

**修複方向**：
- 在整合前過濾空結果
- 截斷過長的 unit output
- 明確指示 LLM 哪些 unit 已成功

---

### D18. C3 — `_format_tool_call` 的格式解析不一致

**位置**：`executor.py:25-43`

```python
@staticmethod
def _format_tool_call(tc: Any) -> dict | None:
    if hasattr(tc, "function"):
        func = tc.function
        return {"name": func.name, "arguments": func.arguments}
    if isinstance(tc, dict):
        return {
            "name": tc.get("function", {}).get("name", ""),
            "arguments": tc.get("function", {}).get("arguments", {}),
        }
    return None
```

**問題描述**：
同時支援 object 和 dict 兩種格式，但：
1. `tc.function.arguments` 可能是 JSON string 或 dict（不確定性）
2. 兩種格式的錯誤處理不一致（object 格式沒有 `json.loads`）

**修複方向**：統一為單一格式

---

### D19. C4 — bootstrap.py 的模組組裝是 tight coupling

**位置**：`bootstrap.py:21-50`

**問題描述**：
所有模組都在 `build_orchestrator()` 中硬編碼組裝。如果要替換任意模組（如使用其他 embedding 實現），必須修改 bootstrap.py。

**修複方向**：使用 dependency injection container 或 factory pattern

---

### D20. C4 — config.py 的常數未做驗證

**位置**：`config.py`

**問題描述**：
所有模型參數（temperature、max_tokens 等）都是常數。如果 Ollama API 支援的參數範圍變化（例如 max_tokens 上限變更），系統不會發出警告。

**修複方向**：在啟動時驗證所有 config 值在 API 支援範圍內

---

## 缺陷總覽

| 編號 | 嚴重度 | 分類 | 問題 | 位置 |
|------|--------|------|------|------|
| D1 | C1 | 單點故障 | session_id 在所有輪次共享，trace 無效 | orchestrator.py:58 |
| D2 | C1 | 單點故障 | asyncio.create_task fire-and-forget 可能被 GC | orchestrator.py:193 |
| D3 | C2 | 單點故障 | Ollama 無服務時系統完全崩潰 | 全域 |
| D4 | C2 | 單點故障 | MCP Server 初始化無 partial fallback | tool_manager.py |
| D5 | C2 | 資料一致性 | trace.jsonl 與 task_trace.jsonl session_id 不同步 | tracer.py |
| D6 | C2 | 資料一致性 | Summarizer add_cache 先於 LLM 呼叫，失敗時資料丟失 | summarizer.py:27-34 |
| D7 | C3 | 資料一致性 | Skill Guide concurrent write race condition | skill_manager.py |
| D8 | C2 | 錯誤處理 | Agentic Loop 最多 20 次 LLM 呼叫/step，成本不可控 | executor.py:386 |
| D9 | C2 | 錯誤處理 | `_is_error_result` 誤判率高 | executor.py:461 |
| D10 | C3 | 錯誤處理 | Clarifier JSON parsing 失敗無 fallback | clarifier.py |
| D11 | C3 | 錯誤處理 | Router pattern match 無 fallback | router.py |
| D12 | C3 | 效能瓶頸 | 每輪呼叫 new_session() 重設 tracer | orchestrator.py:58 |
| D13 | C3 | 效能瓶頸 | Retriever 無 cache，每次搜尋全量向量庫 | retriever.py |
| D14 | C3 | 效能瓶頸 | re-plan 缺少完整上下文 | executor.py:212 |
| D15 | C4 | 效能瓶頸 | StepStore/UnitStore 記憶體儲存無上限 | storage.py |
| D16 | C2 | 設計債 | Optimizer verify 用 heuristic 而非 LLM-as-judge | optimizer.py |
| D17 | C3 | 設計債 | Responder.integrate 對空結果/超长輸出無處理 | responder.py |
| D18 | C3 | 設計債 | `_format_tool_call` 格式不統一 | executor.py:25 |
| D19 | C4 | 設計債 | bootstrap.py tight coupling | bootstrap.py |
| D20 | C4 | 設計債 | config 常數無 API 範圍驗證 | config.py |

---

## 優先修複建議

### 立即（不影響系統可用性但會導致資料損失）
1. **D2**：修复 fire-and-forget task 被 GC 問題
2. **D6**：調整 Summarizer 的 add_cache / LLM call 順序

### 短期（影響系統穩定性）
3. **D3**：加入 Ollama health check 和 fallback
4. **D8**：限制 Agentic Loop 的總成本/時間
5. **D1**：重構 session_id 管理

### 中期（改善品質與維護性）
6. **D16**：Optimizer verify 改為 LLM-as-judge
7. **D5/D12**：統一 tracer session context

---

*分析時間：2026-05-21*
*分析範圍：根據 docs/architecture.md 對照實際程式碼*
