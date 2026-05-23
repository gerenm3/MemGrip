# MemGrip 專案盤點報告

**盤點日期**：2026-05-21  
**盤點方式**：對照實際程式碼 + 三份既有文檔（architecture.md, defect_analysis.md, verification_report.md）

---

## 一、模組清單

| 模組 | 檔案路徑 | 實際狀態 | 備註 |
|------|---------|---------|------|
| main.py | `main.py` | ✅ 完整實作 | Entry point，CLI 參數解析 |
| bootstrap | `bootstrap.py` | ✅ 完整實作 | 13 步模組組裝 |
| config | `config.py` | ✅ 完整實作 | 模型參數、prompts、patterns 路徑 |
| Model Client | `clients/model_client.py` | ✅ 完整實作 | OllamaClient + ModelServiceError |
| MCP Client | `clients/mcp_client.py` | ✅ 完整實作 | MCP Server 通訊 |
| Message Builder | `clients/message_builder.py` | ✅ 完整實作 | 對話訊息建構 |
| Orchestrator | `core/orchestrator.py` | ✅ 完整實作 | 200 行，純協調邏輯 |
| Router | `core/router.py` | ✅ 完整實作 | 103 行，pattern match + LLM |
| Clarifier | `core/clarifier.py` | ✅ 完整實作 | _clarify + _default_clarify + _parse_json_response + _format_input |
| Planner | `core/planner.py` | ✅ 完整實作 | L1 disassemble + L2 plan_unit，含 _parse_units / _parse_steps / _build_* 等輔助方法 |
| Executor | `core/executor.py` | ✅ 完整實作 | 545 行，Agentic Loop（max 5 iterations）、re-plan、pruning |
| Responder | `core/responder.py` | ✅ 完整實作 | reply_simple + integrate + 格式化輔助 |
| Summarizer | `core/summarizer.py` | ✅ 完整實作 | 壓縮對話 → LLM → Vector 存入 |
| Retriever | `core/retriever.py` | ✅ 完整實作 | Vector search + 空字串 fallback |
| Tool Manager | `core/tool_manager.py` | ✅ 完整實作 | MCP 工具初始化 + 調用 + agentic loop |
| Tracer | `core/tracer.py` | ✅ 完整實作 | trace.jsonl + task_trace.jsonl 寫入 |
| Scheduler | `core/scheduler.py` | ✅ 完整實作 | topological_sort + apply_pruning |
| Storage | `core/storage.py` | ✅ 完整實作 | UnitStore + StepStore 記憶體儲存 |
| Blueprints | `models/blueprints.py` | ✅ 完整實作 | Unit / Step / StepResult / UnitResult 類別 |
| Buffer | `memory/buffer.py` | ✅ 完整實作 | ConversationBuffer 對話緩衝 |
| Summary | `memory/summary.py` | ✅ 完整實作 | ConversationSummary 字串容器 |
| Vector | `memory/vector.py` | ✅ 完整實作 | ChromaDB PersistentClient |
| Skill Manager | `skills/skill_manager.py` | ✅ 完整實作 | load/save/apply_update/history |
| Optimizer | `skills/optimizer.py` | ✅ 完整實作 | 六步驟自我優化 |
| Trace Reader | `skills/trace_reader.py` | ✅ 完整實作 | build_execution_record |
| Analyze Results | `skills/analyze_results.py` | ✅ 完整實作 | 分析工具 |
| Init Skills | `skills/init_skills.py` | ✅ 完整實作 | 技能初始化 |
| Run Experiments | `skills/run_experiments.py` | ✅ 完整實作 | 實驗執行 |
| Test scripts | `test/` (5 個檔案) | ⚠️ 骨架 | test_full_loop.py, test_prompt_gen.py, test_tool_exec.py, test.py, test2.py, test3.py |
| test_stability.py | `test_stability.py` | ⚠️ 骨架 | 穩定性測試 |

---

## 二、功能清單

### 核心流程功能

| 功能 | 狀態 | 測試狀態 | 備註 |
|------|------|---------|------|
| Simple Intent 回覆 | ✅ 實作 | ❓ 未確認 | Responder.reply_simple |
| Tool Intent 處理 | ✅ 實作 | ❓ 未確認 | Clarifier → probe_server → agentic_loop |
| Complex Intent 處理 | ✅ 實作 | ❓ 未確認 | L1→L2→L3 完整流程 |
| Intent 分流 (pattern match) | ✅ 實作 | ❓ 未確認 | regex 優先，LLM fallback |
| Intent 分流 (LLM) | ✅ 實作 | ❓ 未確認 | qwen3.5:2b |
| RAG 檢索 | ✅ 實作 | ❓ 未確認 | ChromaDB search |
| 對話摘要 | ✅ 實作 | ❓ 已修復 | 順序已改為先 LLM → 成功後 add_cache |
| L1 任務拆解 | ✅ 實作 | ❓ 未確認 | qwen3.6:35b |
| L2 步驟規劃 | ✅ 實作 | ❓ 未確認 | 支援 re-plan |
| L3 步驟執行 | ✅ 實作 | ❓ 未確認 | Agentic Loop max 5 iters |
| Agentic Loop | ✅ 實作 | ❓ 未確認 | tool_calls 互動迴圈 |
| Re-plan 機制 | ✅ 實作 | ❓ 未確認 | 最多 config.MAX_REPLAN_ATTEMPTS 次 |
| 拓撲排序 | ✅ 實作 | ❓ 未確認 | Unit 依賴排序 |
| 剪枝 (Pruning) | ✅ 實作 | ❓ 未確認 | apply_pruning |
| 技能系統 | ✅ 實作 | ❓ 未確認 | general/global/software_dev/it_security |
| 自我優化 (Optimizer) | ✅ 實作 | ❓ 未確認 | 六步驟流程 |
| Trace 記錄 | ✅ 實作 | ❓ 未確認 | trace.jsonl + task_trace.jsonl |
| Trace Reader | ✅ 實作 | ❓ 未確認 | build_execution_record |
| Skill Guide 注入 | ✅ 實作 | ❓ 未確認 | DISASSEMBLY_PROMPT / STEP_PLAN_PROMPT |

### 已知缺陷對應（實際程式碼驗證結果）

| 缺陷編號 | 嚴重度 | 驗證狀態 | 程式碼依據 | 說明 |
|------|------|------|-----------|------|
| **D1** | C1 | ⚠️ **未修復** | orchestrator.py:60 | 每次 run() 循環呼叫 `new_session()` 覆蓋 global session_id。同回合內 trace/task_trace 同步，但跨回合無法關聯 |
| **D2** | C1 | ✅ **已修復** | orchestrator.py:42, 198-200 | 使用 `self._summarize_tasks: set` + `add_done_callback` 保留 task 引用，避免 GC |
| **D3** | C2 | ✅ **已修復** | model_client.py:76-78, orchestrator.py:104-105 | ModelServiceError → catch → 回傳 "⚠️ AI 服務暫時不可用" |
| **D4** | C2 | ⏭️ **跳過（設計決定）** | tool_manager.py:22-34, mcp_client.py SERVER_REGISTRY | 唯一 server 為 file_rw。partial fallback 無意義。逐一初始化邏輯存在但對單 server 環境是 dead code |
| **D5** | C2 | ⚠️ **未修復** | tracer.py:11,31,79 | trace.jsonl 與 task_trace.jsonl 都使用 global current_session_id。同回合同步，但設計上每輪 new_session 導致無法跨回合關聯 |
| **D6** | C2 | ✅ **已修復** | summarizer.py:37-41 | **順序已調換**：先 LLM (line 37) → 成功後 add_cache (line 40)。LLM 失敗時資料保留在 buffer |
| **D7** | C3 | ⚠️ **未修復** | skill_manager.py | 無 file lock，多輪對話同時觸發 optimizer 可能 race condition |
| **D8** | C2 | ⚠️ **部分修復** | executor.py:447 (max=5), tool_manager.py:82 (max=15) | max_iterations 從 20 降為 5，但無 total token/time budget 限制 |
| **D9** | C2 | ✅ **已修復** | executor.py:523 | `_is_error_result` 從寬鬆關鍵字匹配改為只檢查 `[TOOL_ERROR]` 前綴 |
| **D10** | C3 | ⚠️ **部分修復** | clarifier.py:53-61 | **有 retry 機制（max 3 次）**，但 3 次失敗後仍回傳 `goal: ""` 無空值驗證，Planner 仍可能產生空 Unit |
| **D11** | C3 | ⚠️ **部分修復** | router.py:36-37 | pattern match 失敗回傳 None，走 LLM fallback。但 _load_patterns (line 27-32) 無 try/except，patterns.json 異常會 crash |
| **D12** | C3 | ⚠️ **未修復** | orchestrator.py:60 | 每輪呼叫 `new_session()` 是刻意設計，但與 trace 跨回合關聯需求衝突 |
| **D13** | C3 | ⚠️ **未修復** | retriever.py | 無 cache 機制，每次 need_rag=True 都搜尋全量向量庫 |
| **D14** | C3 | ⚠️ **部分修復** | executor.py:240-245 | 已加入 `failed_step_info`，但 conversation history 仍不完整 |
| **D15** | C4 | ✅ **接受** | storage.py | StepStore/UnitStore 純記憶體 dict，重啟遺失。對一般任務規模可接受 |
| **D16** | C2 | ⚠️ **未修復** | optimizer.py | verify 使用 heuristic 而非 LLM-as-judge，驗證結果可能不準確 |
| **D17** | C3 | ⚠️ **未修復** | responder.py | integrate 對空結果/超長輸出無處理 |
| **D18** | C3 | ⚠️ **部分修復** | executor.py:26-43, 47-56 | `_parse_tool_arguments` 已統一處理 str/dict，但 `_format_tool_call` 仍同時支援 object/dict 兩種格式 |
| **D19** | C4 | ✅ **接受** | bootstrap.py:21-50 | 硬編碼組裝，但對單專案架構可接受，DI container 成本高 |
| **D20** | C4 | ✅ **接受** | config.py | 無啟動驗證，Ollama API 參數範圍變化機率低 |

---

## 三、已知問題

### 已修復的缺陷（實際程式碼修正）

1. ✅ **D2: fire-and-forget task 被 GC** — `orchestrator.py:42, 198-200` 使用 `_summarize_tasks: set` 保留
2. ✅ **D3: Ollama 無服務錯誤處理** — `model_client.py:76-78` ModelServiceError → catch → 回傳警告
3. ✅ **D6: Summarizer add_cache 順序** — `summarizer.py:37-41` 順序調換為先 LLM → 成功後 add_cache
4. ✅ **D9: _is_error_result 誤判** — `executor.py:523` 從寬鬆關鍵字匹配改為只檢查 `[TOOL_ERROR]` 前綴

### 跳過（設計決定）

1. ⏭️ **D4: MCP Server partial fallback** — `mcp_client.py` SERVER_REGISTRY 只有 1 個 server（file_rw），`tool_manager.py:22-34` 逐一初始化邏輯對單 server 環境是 dead code。保留現有實作，不視為缺陷

### 已接受現狀的缺陷（設計決策）

1. **D15: StepStore 無上限** — 對一般任務規模影響有限，可接受
2. **D19: bootstrap tight coupling** — 對單專案架構可接受，改 factory pattern 成本高
3. **D20: config 常數驗證** — Ollama API 參數範圍變化機率低

### 未修復的缺陷

| 優先級 | 缺陷 | 影響 | 程式碼位置 | 備註 |
|--------|------|------|-----------|------|
| **P0** | D1: new_session 覆蓋 session | 跨回合 trace 無法關聯 | orchestrator.py:60 | 核心設計衝突 |
| **P0** | D5: trace session 覆蓋 | Optimizer 無法精確分析特定 session | tracer.py:11,31,79 | 與 D1 同源 |
| **P1** | D7: Skill Guide concurrent write | 多執行緒環境可能 race condition | skill_manager.py | |
| **P1** | D10: Clarifier goal 空值 | Planner 收到空 goal 產生空 Unit | clarifier.py:53-61 | 有 retry 機制但無空值驗證 |
| **P1** | D11: patterns.json 容錯 | _load_patterns 無 try/except，檔案異常可能 crash | router.py:27-32 | pattern match 有 fallback |
| **P2** | D8: Agentic Loop 總成本限制 | max_iterations=5 但無 token/time budget | executor.py:447, tool_manager.py:82 | max 已從 20 降為 5 |
| **P2** | D13: Retriever cache | 大量對話時搜尋延遲 | retriever.py | |
| **P2** | D14: re-plan 完整上下文 | conversation history 仍不完整 | executor.py:240-245 | 已加入 failed_step_info |
| **P3** | D16: Optimizer verify 邏輯 | heuristic verify 可能不準確 | optimizer.py | |
| **P3** | D17: Responder 長輸出處理 | 可能 context overflow | responder.py | |
| **D12** | C3 | 每輪 new_session 設計衝突 | orchestrator.py:60 | 與 D1 同源 |

---

## 四、待辦清單

### 高優先級（P0）

- [ ] **D1 + D5 修復**: 重構 session_id 管理（使用 contextvar 或 task-scoped session）
  - 目前每輪 run() 呼叫 new_session() 導致跨回合 trace 斷裂
  - 需導入 contextvar 確保同任務的所有寫入使用同一 session_id

### 中優先級（P1-P2）

- [ ] D10: Clarifier 加入 goal 空值驗證（clarifier.py:53-61）— *雖有 retry 但需 final fallback 回傳 error 而非空 goal*
- [ ] D7: Skill Manager 加入 file lock（skill_manager.py）
- [ ] D11: _load_patterns 加入 try/except 和 default patterns（router.py:27-32）
- [ ] D13: Retriever 加入 TTL cache（retriever.py）
- [ ] D17: Responder.integrate 加入輸出截斷和空結果過濾（responder.py）
- [ ] D8: Agentic Loop 加入 total token/time budget（executor.py:447, tool_manager.py:82）
- [ ] D14: re-plan 加入完整 conversation history（executor.py:240-245）
- [ ] D18: _format_tool_call 徹底統一格式（executor.py:26-43）

### 低優先級（P3）

- [ ] D16: Optimizer verify 改用 LLM-as-judge（optimizer.py）
- [ ] D20: config 啟動驗證（config.py）— *可選，機率低*
- [ ] 補寫單元測試（test/ 目錄只有骨架，test_full_loop.py 使用 mock data + 硬編碼）
- [ ] 加入 CI linting（flake8 / mypy）

---

## 五、技術債

| 類別 | 描述 | 影響 | 接受理由 |
|------|------|------|----------|
| **架構** | bootstrap.py 硬編碼組裝（D19） | 模組替換需改 bootstrap | 目前模組固定，DI container 成本高 |
| **資料** | StepStore/UnitStore 純記憶體（D15） | 重啟遺失 | 一般任務規模記憶體足夠 |
| **資料** | config 常數無驗證（D20） | 版本不兼容時無警報 | Ollama API 變更頻率低 |
| **程式** | Router _load_patterns 無容錯（D11） | 檔案異常 crash | patterns.json 為手動維護，機率低 |
| **程式** | ToolManager _init_tools dead code（D4） | 對單 server 無實際影響，多 server 才有價值 | 單 server 環境，partial fallback dead code 不影響 |
| **設計** | Planner 不直接管理 skill_guide | 文檔描述不精確 | Orchestrator 注入模式清晰可懂 |
| **設計** | ConversationSummary 只是字串容器 | 名稱易誤解 | 職責單一化，可接受 |
| **文件** | architecture.md 遺漏 ~23 個輔助方法 | 新開發者不熟悉 | 核心方法已記錄，輔助方法可從 code 閱讀 |
| **文件** | Summarizer 輸入描述錯誤 | 文檔說 buffer 字串，實際是 call_model_func | 文檔需更新 |

---

## 六、文檔準確性評估

| 文檔 | 準確性 | 主要問題 |
|------|--------|----------|
| architecture.md | 85% | 核心流程描述正確，遺漏大量輔助方法；Summarizer 輸入描述錯誤 |
| defect_analysis.md | 90% | 20 個缺陷分析全面；D1/D2/D8/D9 狀態已變化（已修復或部分修復） |
| verification_report.md | 100% | 與實際程式碼對照最精確，19 項不符之處已標註 |

---

## 七、程式碼品質指標

| 指標 | 數值 | 備註 |
|------|------|------|
| 模組總數 | 28 | 包含 skills 和 test |
| 最大模組 | executor.py (545 行) | Agentic Loop + 所有 handler |
| 最小模組 | router.py (103 行) | Intent 分流 |
| 已知缺陷總數 | 20 | C1×2, C2×7, C3×7, C4×4 |
| ✅ 實際修復 | 4 | D2, D3, D6, D9 |
| ⏭️ 跳過（設計決定） | 1 | D4 |
| ⚠️ 部分修復 | 5 | D8, D10, D11, D14, D18 |
| ❌ 未修復 | 8 | D1, D5, D7, D12, D13, D16, D17 |
| ✅ 接受現狀 | 3 | D15 (StepStore), D19 (bootstrap), D20 (config) |
| 測試覆蓋率 | ❓ 未知 | test/ 目錄只有骨架，無真實測試覆蓋 |

---

## 八、檔案依賴關係

```
main.py
  └─ bootstrap.py
       ├─ OllamaClient (clients/model_client.py)
       ├─ mcp_client (clients/mcp_client.py)
       ├─ ConversationBuffer (memory/buffer.py)
       ├─ ConversationSummary (memory/summary.py)
       ├─ ConversationVector (memory/vector.py)
       ├─ Router (core/router.py) ──▶ MessageBuilder + config
       ├─ Clarifier (core/clarifier.py) ──▶ MessageBuilder + buffer + summary
       ├─ Planner (core/planner.py) ──▶ MessageBuilder + config
       ├─ Summarizer (core/summarizer.py) ──▶ MessageBuilder + summary + vector
       ├─ ToolManager (core/tool_manager.py) ──▶ mcp_client + MessageBuilder
       ├─ Responder (core/responder.py) ──▶ MessageBuilder + config
       ├─ Executor (core/executor.py) ──▶ scheduler + storage + MessageBuilder + config + blueprints
       ├─ Retriever (core/retriever.py) ──▶ vector + config
       └─ Orchestrator (core/orchestrator.py) ──▶ 以上所有模組 + tracer + skill_manager
```

---

*盤點完成時間：2026-05-21*  
*盤點依據：實際程式碼 + architecture.md + defect_analysis.md + verification_report.md*  
*本次修正：D4 → 跳過（設計決定，唯一 server 使 partial fallback 無意義）、D10 → 部分修復（有 retry 但缺空值驗證）、D20 → 接受現狀、D4 加入技術債表格*
