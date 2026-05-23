# MemGrip 架構文件

MemGrip 是一個基於 LLM（Ollama）的 AI 任務協調器（Orchestrator），具備多輪對話、RAG（檢索增強生成）、任務拆解、Agentic Loop 與自我優化能力。

---

## 一、模組清單

### 1. 核心協調層

#### Orchestrator（core/orchestrator.py）

- **職責**：純協調邏輯，不初始化任何模組實例。統一路徑調度所有模組，根據意圖分流處理。
- **輸入**：user_input（字串）、intent（simple/tool/complex）、rag_content（字串）
- **輸出**：reply（字串）
- **關鍵方法**：
  - `run()`：互動式主循環
  - `_dispatch_by_intent()`：依意圖分流至不同 handler
  - `_handle_simple_intent()`：直接回覆
  - `_handle_tool_intent()`：工具調用迴圈
  - `_handle_complex_intent()`：L1→L2→L3 完整流程

#### Router（core/router.py）

- **職責**：Intent 分流與 RAG 必要性的判斷。先比對 regex pattern（patterns.json），再呼叫 LLM 分類。
- **輸入**：user_input（字串）
- **輸出**：`{intent: str, need_rag: bool}`
- **關鍵方法**：
  - `route()`：主入口，返回 intent + need_rag
  - `_pattern_match()`：regex 比對優先於 LLM
  - `probe_server()`：從多個 MCP server 中挑出最相關的目標

#### Clarifier（core/clarifier.py）

- **職責**：將用戶輸入轉為結構化欄位。整合 buffer、summary、user_input，呼叫 LLM 分析出 goal、entities、scope 等。
- **輸入**：user_input（字串）
- **輸出**：`{goal, entities, scope, constraints, rules, success_criteria, questions}`
- **關鍵方法**：
  - `_clarify()`：主入口，整合所有上下文後呼叫 LLM
  - `_parse_json_response()`：解析 LLM 回傳 JSON

### 2. 規劃層（Planning）

#### Planner - L1（core/planner.py）

- **職責**：戰略拆解（Disassembly）。將一個複雜任務拆成多個可並行/依序執行的 Unit。
- **輸入**：goal, entities, scope, constraints, success_criteria, tools, skill_guide
- **輸出**：`List[Unit]`
- **關鍵方法**：
  - `disassemble()`：呼叫 LLM 產生 Unit 陣列
  - `_parse_units()`：解析 JSON 回傳為 Unit 物件

#### Planner - L2（core/planner.py）

- **職責**：戰術規劃。對單一 Unit 規劃具體執行步驟（Steps），包含工具調用順序與依賴關係。
- **輸入**：unit, tools_list, successful_steps（可選，用於 re-plan）
- **輸出**：`List[Step]`
- **關鍵方法**：
  - `plan_unit()`：對單一 Unit 規劃 Steps

### 3. 執行層（Execution）

#### Executor（core/executor.py）

- **職責**：L3 執行器。負責 Unit 內 Step 的執行與 Agentic Loop。包含拓撲排序、依賴檢查、re-plan 機制、剪枝（pruning）。
- **輸入**：`List[Unit]`, `server_schemas`
- **輸出**：`Dict[str, UnitResult]`（unit_id → UnitResult 對應）
- **關鍵方法**：
  - `execute_units()`：主入口，兩階段執行（L2 規劃 → L3 執行）
  - `_execute_unit_steps()`：執行單一 Unit 的所有 Steps
  - `_execute_step()`：執行單一 Step（含 Agentic Loop）
  - `_run_agentic_loop()`：LLM + 工具調用的互動迴圈

#### ToolManager（core/tool_manager.py）

- **職責**：MCP Server 工具管理。初始化 tools、調用工具、執行 agentic loop 回覆。
- **輸入**：tool_name, tool_arguments
- **輸出**：tool_result（字串）
- **關鍵方法**：
  - `_init_tools()`：初始化 MCP Server 並載入 tool schemas
  - `execute_tool()`：單一工具調用
  - `run_agentic_loop()`：工具調用迴圈

### 4. 回應層（Response）

#### Responder（core/responder.py）

- **職責**：回覆生成。包含簡單意圖回覆與複雜任務結果整合。
- **輸入**：
  - `reply_simple()`: system_prompt, user_input, summary, buffer, rag
  - `integrate()`: original_task, results, units
- **輸出**：reply（字串）
- **關鍵方法**：
  - `reply_simple()`：直接呼叫 LLM 回覆
  - `integrate()`：整合所有 Unit 結果，呼叫 LLM 產出最終回覆

### 5. 記憶層（Memory）

#### Buffer（memory/buffer.py）

- **職責**：短期對話記憶。儲存最近的對話紀錄，超出容量時觸發摘要。
- **輸入**：role（user/assistant）, content（字串）
- **輸出**：序列化字串（供其他模組使用）
- **關鍵方法**：
  - `add()`：加入對話紀錄
  - `serialize()`：輸出序列化字串
  - `storage()`：儲存狀態

#### Summary（memory/summary.py）

- **職責**：長期記憶摘要容器。僅作為摘要字串的字串容器，不具備任何摘要壓縮邏輯（摘要壓縮由 Summarizer 處理）。
- **輸入**：`summary`（摘要字串）
- **輸出**：摘要字串
- **關鍵方法**：
  - `get_summary()`：取得當前摘要
  - `set_summary(summary)`：設定摘要字串
  - `add_cache()`：快取已 flush 的對話紀錄
  - `cached_flushed`：已快取的對話紀錄列表

#### Vector（memory/vector.py）

- **職責**：向量資料庫。儲存對話的 embedding 向量，支援相似度搜尋。
- **輸入**：text → embedding（List[float]）
- **輸出**：相似度搜尋結果
- **關鍵方法**：
  - 呼叫 Ollama embedding API

### 6. 檢索與摘要層

#### Retriever（core/retriever.py）

- **職責**：RAG 上下文檢索。當 Router 判斷 need_rag=True 時，使用 Vector 搜尋相關對話。
- **輸入**：user_input（字串）
- **輸出**：rag_content（字串）
- **關鍵方法**：
  - `retrieve()`：搜尋並返回相關上下文

#### Summarizer（core/summarizer.py）

- **職責**：對話摘要與向量存入。將 flushed 對話輪廓壓縮為摘要，經相似度與重要性檢查後存入 Vector。
- **輸入**：`call_model_func`（LLM 呼叫函式）、`call_embedding_func`（embedding 函式）、`summary`（ConversationSummary 實例）、`vector`（ConversationVector 實例）
- **輸出**：無（副作用：更新 summary 物件與向量庫）
- **關鍵方法**：
  - `summarize(flushed)`：主流程 — addCache → formatTurns → buildMetaPrompt → callLLM → setSummary → embed → compareSimilarity → checkImportance → addVector
  - `_format_turns()`：格式化對話輪廓
  - `_check_importance()`：呼叫 LLM 檢查摘要重要性
  - `_call_llm()`：封裝 LLM 呼叫
- **注意**：`__init__` 的 `summary` 參數是 ConversationSummary 實例（非字串），`call_model_func` 是函式而非 buffer 字串

### 7. 追蹤層（Tracing）

#### Tracer（core/tracer.py）

- **職責**：執行追蹤記錄。記錄每次 LLM 呼叫的完整資訊（messages, tool_calls, response），寫入 trace.jsonl。任務層級的記錄寫入 task_trace.jsonl。
- **輸入**：caller, unit_id, step_id, messages, response, tool_calls
- **輸出**：寫入 trace.jsonl 與 task_trace.jsonl
- **關鍵方法**：
  - `new_session()`：建立新 session
  - `log_task()`：寫入任務層 trace
  - `log_model_call()`：寫入單次 LLM 呼叫記錄（caller, unit_id, step_id, messages, response, tool_calls, ts）

### 8. 技能層（Skills）

#### SkillManager（skills/skill_manager.py）

- **職責**：skill_guide 的存取管理。負責載入、儲存、更新 skill 指導文件（JSON 格式）。
- **輸入**：task_type（general/global/software_dev/it_security）
- **輸出**：skill_guide（dict）
- **關鍵方法**：
  - `load_skill()`：載入當前 skill（不存在時從 global 複製）
  - `save_skill()`：儲存 skill
  - `apply_update()`：套用優化結果並儲存歷史
  - `skill_guide_to_prompt()`：將 skill_guide 轉為可注入 prompt 的文字

#### Optimizer（skills/optimizer.py）

- **職責**：自我優化引擎。依六步驟分析任務執行結果，診斷問題，更新 skill_guide。
- **輸入**：session_id（字串）、task_type（字串）
- **輸出**：`(dimension_map, update_result)` 或 `(error, None)`
- **關鍵方法**：
  - `run_optimizer()`：完整六步驟流程

#### TraceReader（skills/trace_reader.py）

- **職責**：從 trace.jsonl 與 task_trace.jsonl 組裝 execution_record。
- **輸入**：session_id（字串）
- **輸出**：`{task_type, goal, units: [{unit_id, planned_goal, expected_output, actual_output, status, steps: [...]}]}`

---

## 二、執行流程

### 整體架構圖

```
┌──────────────────────────────────────────────────────────────────┐
│                        main.py (Entry Point)                     │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                     bootstrap.py                         │   │
│   │   組裝所有模組 → 回傳 Orchestrator                      │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   ┌───────────────┐    ┌───────────────┐                        │
│   │ Interactive   │    │ Non-Interactive│                       │
│   │ (orchestrator.│    │ (run_task_mode)│                       │
│   │  run())       │    │               │                        │
│   └───────┬───────┘    └───────┬───────┘                        │
│           │                     │                               │
│           └──────────┬──────────┘                               │
│                      ▼                                          │
│              ┌───────────────┐                                 │
│              │   Router      │  ← patterns.json               │
│              │  (intent)     │                                 │
│              └───────┬───────┘                                 │
│                      ▼                                          │
│              ┌───────────────┐                                 │
│              │   Retriever   │  ← Vector (RAG)               │
│              │  (need_rag?)  │                                 │
│              └───────┬───────┘                                 │
│                      ▼                                          │
│   ┌──────────────────┼──────────────────┐                     │
│   │                   │                   │                     │
│   ▼                   ▼                   ▼                     │
│  Simple              Tool             Complex                    │
│   │                   │                   │                     │
│   ▼                   ▼                   ▼                     │
│ Responder        Clarifier          Clarifier                   │
│                      │                   │                       │
│                      ▼                   ▼                       │
│              Probe Server         Planner (L1)                   │
│                            ┌─────────────────┐                  │
│                            │   Skill Guide    │ ← skill_manager │
│                            └────────┬─────────┘                  │
│                                     ▼                            │
│                           Planner (L2)                           │
│                                     ▼                            │
│                           Executor (L3)                          │
│                        ┌──┴──────────────┐                      │
│                        │  Agentic Loop    │                     │
│                        │  + ToolManager   │                     │
│                        └────────┬─────────┘                      │
│                                 ▼                               │
│                          Responder (Integrate)                   │
│                                 ▼                               │
│                            User Output                           │
└──────────────────────────────────────────────────────────────────┘
```

### 流程 1：互動式模式（Interactive Mode）

```
1. 用戶輸入 ──────────────────────────────────────────────────┐
                                                              │
2. ┌─ Router.route() ──────────────────────────────┐         │
   │                                                │         │
   │  Step 1: 比對 patterns.json (regex)           │         │
   │         → 有匹配：直接回傳 intent + need_rag   │         │
   │         → 無匹配：呼叫 LLM 分類                 │         │
   │                                                │         │
   │  Step 2: LLM 判斷 intent ──────────┐          │
   │                  ↓                  │          │
   │            {simple, tool, complex}  │          │
   │                                      │          │
   │  Step 3: LLM 判斷 need_rag ────────┘          │
   │                  ↓                              │
   │            {true, false}                        │
   │                                                │
   └────────────────────────────────────────────────┘         │
                                                              │
3. ┌─ Retriever.retrieve() ──────────────────────────┐       │
   │   (if need_rag == true)                          │       │
   │                                                    │       │
   │   以 user_input 搜尋 Vector ──▶ rag_content       │       │
   │                                                    │       │
   └────────────────────────────────────────────────────┘       │
                                                              │
4. ┌─ Intent Dispatch ──────────────────────────────┐        │
   │                                                  │        │
   │   ┌─ Simple Intent ─────────────────────────┐   │        │
   │   │                                           │   │        │
   │   │  Responder.reply_simple(                  │   │        │
   │   │    system_prompt, user_input,             │   │        │
   │   │    summary, buffer, rag_content            │   │        │
   │   │  ) ──▶ LLM → reply                        │   │        │
   │   │                                           │   │        │
   │   └───────────────────────────────────────────┘   │        │
   │                                                  │        │
   │   ┌─ Tool Intent ───────────────────────────┐   │        │
   │   │                                           │   │        │
   │   │  Clarifier._clarify() ──▶ {goal, ...}    │   │        │
   │   │     ↓                                     │   │        │
   │   │  Router.probe_server() ──▶ server_name   │   │        │
   │   │     ↓                                     │   │        │
   │   │  ToolManager.run_agentic_loop(            │   │        │
   │   │      goal, server_tools                   │   │        │
   │   │  ) ──▶ Agentic Loop ──▶ reply            │   │        │
   │   │                                           │   │        │
   │   └───────────────────────────────────────────┘   │        │
   │                                                  │        │
   │   ┌─ Complex Intent ────────────────────────┐   │        │
   │   │                                           │   │        │
   │   │  Clarifier._clarify() ──▶ {goal, ...}    │   │        │
   │   │     ↓                                     │   │        │
   │   │  load_skill(task_type) ──▶ skill_guide   │   │        │
   │   │     ↓                                     │   │        │
   │   │  Planner.disassemble( ──▶ List[Unit]     │   │        │
   │   │    goal, entities, scope, constraints,    │   │        │
   │   │    success_criteria, tools, skill_guide)  │   │        │
   │   │     ↓                                     │   │        │
   │   │  Executor.execute_units( ──▶ Dict[uid,   │   │        │
   │   │    units, server_schemas)    UnitResult]  │   │        │
   │   │     ↓                                     │   │        │
   │   │  log_task(task_type, goal, results)       │   │        │
   │   │     ↓                                     │   │        │
   │   │  Responder.integrate( ──▶ LLM ──▶ reply  │   │        │
   │   │    original_task, results, units)         │   │        │
   │   │                                           │   │        │
   │   └───────────────────────────────────────────┘   │        │
   │                                                  │        │
   └──────────────────────────────────────────────────┘        │
                                                              │
5. ┌─ 儲存與追蹤 ───────────────────────────────────┐       │
   │                                                  │       │
   │  buffer.add("user", user_input)                  │       │
   │  buffer.add("assistant", reply)                  │       │
   │  _summarize_if_needed() ──▶ Summarizer          │       │
   │                                                  │       │
   └──────────────────────────────────────────────────┘       │
                                                              │
6. ┌─ 主循環 ───────────────────────────────────────┐       │
   │                                                  │       │
   │  回到步驟 1，等待下一輪輸入                       │       │
   │                                                  │       │
   └──────────────────────────────────────────────────┘       │
                                                              │
```

### 流程 2：非互動式模式（Non-Interactive Mode）

```
1. 接收 --task 參數 ──▶ run_task_mode(orchestrator, task)

2. ToolManager._init_tools()

3. Router.route(task) ──▶ intent, need_rag (無 RAG)

4. 依 intent 分流 ──▶ _dispatch_by_intent(intent, task, "")

5. buffer.add() + _summarize_if_needed()

6. 印出結果 → 退出
```

### 流程 3：Executor 執行流程（L2 + L3）

```
Executor.execute_units(units, server_schemas):

  ┌─── 第一階段：L2 規劃所有 Units ────────────────────────┐
  │                                                          │
  │  for unit in topological_sort(units):                   │
  │    ├── should_skip(unit)? ──▶ yes → 剪枝 (SKIPPED)     │
  │    ├── get_tools_for_server(unit.mcp_server)           │
  │    ├── planner.plan_unit(unit, tools_list)             │
  │    │   └── ▶ List[Step]                               │
  │    └── store in unit_steps                              │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
                              │
  ┌─── 第二階段：L3 統一執行所有 Units ────────────────────┐
  │                                                          │
  │  for unit in topological_sort(units):                   │
  │    ├── collect_upstream_outputs(unit)                   │
  │    ├── step_store = StepStore(unit_id)                 │
  │    ├── current_step_idx = 0                            │
  │    │                                                  │
  │    │  while current_step_idx < len(steps):            │
  │    │    ├── check_dependencies(step)                  │
  │    │    ├── _execute_step(step) ──▶ Agentic Loop      │
  │    │    │   └── ▶ StepResult                         │
  │    │    │                                          │
  │    │    └── if failed and replan_attempts < max:     │
  │    │         ├── planner.plan_unit(unit, tools,      │
  │    │    │    successful_steps) ──▶ re-plan Steps    │
  │    │         └── retry from current step             │
  │    │                                              │
  │    └── check_global_output(unit) ──▶ SUCCESS/FAILED  │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
                              │
  ┌─── 剪枝 ──────────────────────────────────────────────┐
  │                                                          │
  │  apply_pruning(units, results) ──▶ 過濾失敗單元        │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
                              │
                    return Dict[unit_id, UnitResult]
```

---

## 三、資料流：trace.jsonl、task_trace.jsonl、skill_guide

### 三者關係圖

```
                        ┌──────────────────────────────┐
                        │        用戶任務執行            │
                        └──────────┬───────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                     ▼
     ┌─────────────────┐  ┌──────────────────┐  ┌──────────────┐
     │  core/tracer.py  │  │  core/tracer.py  │  │ skill_guide  │
     │  (trace logging) │  │  (task logging)  │  │ (planning    │
     └────────┬─────────┘  └────────┬─────────┘  │  guidance)   │
              │                      │             └──────┬─────┘
              ▼                      ▼                    │
     ┌─────────────────┐  ┌──────────────────┐            │
     │  trace.jsonl    │  │  task_trace.jsonl│  ┌─────────▼───────┐
     │                  │  │                  │  │  planner.py     │
     │  每筆 LLM 呼叫   │  │  每筆任務紀錄    │  │  (注入到 DISAS- │
     │  - caller        │  │  - session_id    │  │   MBLY_PROMPT) │
     │  - unit_id       │  │  - task_type     │  └─────────────────┘
     │  - step_id       │  │  - goal          │                  │
     │  - messages      │  │  - units[]       │                  │
     │  - tool_calls    │  │    - status      │                  │
     │  - response      │  │    - output      │                  │
     └──────────────────┘  └──────────────────┘                  │
              │                      │                            │
              └──────────┬───────────┘                            │
                         │                                        │
              ┌──────────▼──────────┐                             │
              │  skills/trace_reader│                             │
              │  .py                │                             │
              │                     │                             │
              │  build_execution_   │                             │
              │  record(session_id) │                             │
              │                     │                             │
              │  組合輸出：           │                             │
              │  - planned_goal     │                             │
              │  - expected_output  │                             │
              │  - actual_output    │                             │
              │  - agentic_loop[]   │                             │
              └──────────┬──────────┘                             │
                         │                                        │
              ┌──────────▼──────────┐                             │
              │  skills/optimizer.py│                             │
              │  .py                │                             │
              │                     │                             │
              │  六步驟分析：         │                             │
              │  1. intent_check    │                             │
              │  2. planning_check  │                             │
              │  3. execution_check │                             │
              │  4. map_to_dimensions                          │
              │  5. update_skills   │                             │
              │  6. verify          │                             │
              └──────────┬──────────┘                             │
                         │                                        │
              ┌──────────▼──────────┐                             │
              │  skill_manager.py   │                             │
              │                     │                             │
              │  apply_update()     │                             │
              │  save_history()     │                             │
              │                     │                             │
              │  寫入到：             │                             │
              │  skills/{type}/     │                             │
              │    current.json     │                             │
              │    history/{time}.json                         │
              └─────────────────────┘                             │
```

### trace.jsonl

- **內容**：每筆 LLM 呼叫的詳細記錄
- **欄位**：
  - `session_id`：會話 ID
  - `caller`：呼叫者（router / clarifier / planner_l1 / planner_l2 / executor / integrator）
  - `unit_id`：單元 ID
  - `step_id`：步驟 ID
  - `model`：使用的模型
  - `messages`：完整對話訊息
  - `response`：LLM 回傳內容
  - `tool_calls`：工具調用資訊
  - `ts`：時間戳記（time.time() 格式）
- **寫入時機**：每次 `call_model_func()` 完成後

### task_trace.jsonl

- **內容**：任務層級的完整紀錄
- **欄位**：
  - `session_id`：會話 ID
  - `task_id`：任務 ID（UUID，每次 `log_task()` 產生）
  - `task_type`：任務類型（general / software_dev / it_security）
  - `goal`：任務目標
  - `clarified_goal`：澄清後目標
  - `final_status`：任務最終狀態（"success" 若所有 unit 皆 SUCCESS，否則 "failed"）
  - `units`：
    - `unit_id`：單元 ID
    - `goal`：單元目標
    - `status`：SUCCESS / FAILED / SKIPPED
    - `output`：輸出結果
  - `ts`：時間戳記（time.time() 格式）
- **寫入時機**：`complex` 意圖處理完成後，呼叫 `log_task()`

### skill_guide

- **結構**：五個維度的規劃指導（JSON 格式）
  ```json
  {
    "reasoning_resolution": {
      "core_concept": "...",
      "prompt_patterns": { "direct": "...", "step_by_step": "...", "chain_of_thought": "..." },
      "design_principles": ["..."],
      "pitfalls": ["..."]
    },
    "constraint_rigidity": { ... },
    "signal_noise_ratio": { ... },
    "boundary_anchoring": { ... },
    "uncertainty_handling": { ... }
  }
  ```
- **儲存位置**：`skills/{task_type}/current.json`
- **用途**：注入到 `DISASSEMBLY_PROMPT` 與 `STEP_PLAN_PROMPT`，指導 LLM 如何拆解任務與規劃步驟
- **更新機制**：optimizer 六步驟驗證通過後，由 skill_manager.apply_update() 寫入

---

## 四、Optimizer 六步驟流程

Optimizer 是一個獨立的自我優化引擎，透過分析歷史任務執行記錄，自動診斷問題並更新 skill_guide。

### 流程圖

```
                    ┌─────────────────────────────┐
                    │  run_optimizer(session_id)   │
                    │                              │
                    │  1. build_execution_record() │ ← task_trace.jsonl
                    │     (從 trace + task_trace)    │  + trace.jsonl
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │  步驟一：intent_check          │
                    │                                │
                    │  輸入：execution_record         │
                    │  輸出：{aligned, gaps}         │
                    │                                │
                    │  對比任務意圖 (goal) 與         │
                    │  最終實際輸出 (actual_output)    │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │  步驟二：planning_check        │
                    │                                │
                    │  輸入：execution_record         │
                    │  輸出：{plan_quality,          │
                    │             plan_gaps,          │
                    │             failed_units}       │
                    │                                │
                    │  分析每個 unit 的 planned_goal  │
                    │  與 expected_output 品質        │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │  步驟三：execution_check       │
                    │                                │
                    │  輸入：execution_record         │
                    │  輸出：{tool_usage_quality,     │
                    │             execution_gaps,     │
                    │             missing_tools}      │
                    │                                │
                    │  分析 agentic_loop 中的         │
                    │  工具呼叫品質                    │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │  (以上三步驟並行執行)            │
                    │  asyncio.gather(intent_check,   │
                    │          planning_check,         │
                    │          execution_check)        │
                    └────────────────────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │  步驟四：map_to_dimensions     │
                    │                                │
                    │  輸入：intent_result +           │
                    │             planning_result +   │
                    │             execution_result    │
                    │  輸出：{                         │
                    │     reasoning_resolution: {     │
                    │       problem, direction        │
                    │     },                          │
                    │     constraint_rigidity: {...}, │
                    │     signal_noise_ratio: {...},  │
                    │     boundary_anchoring: {...},  │
                    │     uncertainty_handling: {...} │
                    │   }                            │
                    │                                │
                    │  綜合三個階段診斷，映射到五個    │
                    │  維度，每個維度輸出 problem 與   │
                    │  建議的調整方向                    │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │  步驟五：update_skills         │
                    │                                │
                    │  輸入：dimension_map +           │
                    │             task_type +         │
                    │             current_skill       │
                    │  輸出：{                         │
                    │     modified_dimensions: [...], │
                    │     updated_skills: {...},      │
                    │     change_summary: {...}       │
                    │   }                            │
                    │                                │
                    │  對有問題的維度執行最小修改       │
                    │  （保留原有結構）                 │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │  步驟六：verify                │
                    │                                │
                    │  輸入：update_result +           │
                    │             dimension_map       │
                    │  輸出：{passed, reason}        │
                    │                                │
                    │  驗證更新後的 skill 是否           │
                    │  能解決診斷出的問題               │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │  驗證結果處理                    │
                    │                                │
                    │  ┌─ passed ──┐  ┌─ failed ──┐ │
                    │  │            │  │            │ │
                    │  ▼            ▼  ▼            ▼ │
                    │  寫入         重試         超過 │
                    │  skill_guide  (最多2次)   重試 │
                    │  並存歷史     update+verify    │
                    └────────────────────────────────┘
```

### 六步驟詳細輸入輸出關係

| 步驟 | 函數名稱 | 輸入 | 輸出 | 依賴 |
|------|---------|------|--|------|
| **1** | `intent_check()` | `execution_record`（goal + units） | `{aligned: bool, gaps: [string]}` | 無（並行） |
| **2** | `planning_check()` | `execution_record`（units with planned_goal） | `{plan_quality: string, plan_gaps: [string], failed_units: [string]}` | 無（並行） |
| **3** | `execution_check()` | `execution_record`（units with agentic_loop） | `{tool_usage_quality: string, execution_gaps: [string], missing_tools: [string]}` | 無（並行） |
| **4** | `map_to_dimensions()` | 步驟 1+2+3 的輸出 | `{reasoning_resolution: {problem, direction}, ... (5 dims)}` | 步驟 1, 2, 3 |
| **5** | `update_skills()` | 步驟 4 + task_type + current skill | `{modified_dimensions: [string], updated_skills: {dim: content}, change_summary: {dim: string}}` | 步驟 4 |
| **6** | `verify()` | 步驟 5 + 步驟 4 | `{passed: bool, reason: string}` | 步驟 5 |

### 五個維度定義

| 維度 | 方向範圍 | 描述 |
|------|---------|------|
| **Reasoning Resolution** | `direct` → `step_by_step` → `chain_of_thought` | 模型思考的步長，決定推導過程的顯式程度 |
| **Constraint Rigidity** | `guideline` → `rule` → `hard_schema` | 模型的自由度與合規性的平衡 |
| **Signal-to-Noise Ratio** | `minimal` → `balanced` → `rich` | 核心上下文與邊緣資訊的比例 |
| **Boundary Anchoring** | `happy_path` → `mixed` → `edge_cases` | 典型案例與邊緣案例的比例 |
| **Uncertainty Handling** | `aggressive` → `balanced` → `conservative` | 資訊不足時的行為模式 |

### 重試機制

```
for attempt in range(3):  # 最多 3 次（1 次初始 + 2 次重試）
    update_result = update_skills(dimension_map)
    verify_result = verify(update_result, dimension_map)
    
    if verify_result.passed:
        apply_update(task_type, update_skills)
        save_history(task_type)
        break  # 成功，退出
```

---

## 五、模組依存關係圖

```
                   ┌─────────────────┐
                   │   main.py        │
                   │   bootstrap.py   │
                   └────────┬─────────┘
                            │
                   ┌────────▼─────────┐
                   │  Orchestrator     │
                   └────────┬─────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
   ┌────────┐       ┌────────────┐      ┌───────────┐
   │ Router │       │  Retriever │      │  Buffer   │
   └───┬────┘       └─────┬──────┘      │  Summary  │
       │                   │             └───────────┘
       │                   │
       ▼                   ▼
   ┌────────┐       ┌────────────┐
   │Clarifier│      │   Vector   │
   └───┬─────┘      └────────────┘
       │
       ▼
   ┌────────┐
   │Planner │ ──▶ Skill Guide (skill_manager)
   └───┬────┘
       │
       ▼
   ┌────────┐       ┌────────────┐
   │Executor│ ──▶   ToolManager  │
   └───┬────┘       └────────────┘
       │
       ▼
   ┌────────┐
   │Responder │
   └──────────┘

   所有模組呼叫 → Model Client (Ollama)
   Orchestrator → Tracer (寫入 trace)
```

### 啟動流程（bootstrap）

```python
# bootstrap.py build_orchestrator()
1. new_session()                          # Tracer
2. OllamaClient()                        # Model Client
3. _create_call_model()                  # 統一 LLM 呼叫介面
4. _create_call_embedding()              # 統一 Embedding 介面
5. _create_memory()                      # Buffer + Summary + Vector
6. Router(call_model)                    # Intent 分流
7. Clarifier(call_model, buffer, summary) # 結構化分析
8. Planner(call_model)                   # 任務規劃
9. Summarizer(call_model, call_embed, summary, vector)
10. ToolManager(mcp_client, call_model)  # 工具管理
11. Responder(call_model)                # 回覆生成
12. Executor(call_model, planner, tool_manager.execute_tool)  # 執行器（第三個參數為 tool_manager 的 execute_tool 方法）
13. Orchestrator(以上所有模組)
```

---

## 六、執行時資料流總覽

```
用戶輸入
  │
  ├─▶ [Router] → intent + need_rag
  │
  ├─▶ [Retriever] (若 need_rag) → rag_content
  │     └─ Vector DB 搜尋
  │
  ├─ [Intent: Simple]
  │     └─ [Responder.reply_simple]
  │            └─ 呼叫 LLM (MEDIUM_MODEL)
  │
  ├─ [Intent: Tool]
  │     ├─ [Clarifier] → {goal, entities, ...}
  │     ├─ [Router.probe_server] → server_name
  │     └─ [ToolManager.run_agentic_loop]
  │            └─ MCP tools 調用
  │
  └─ [Intent: Complex]
        ├─ [Clarifier] → {goal, entities, scope, ...}
        ├─ [SkillManager.load_skill] → skill_guide
        ├─ [Planner.disassemble] → List[Unit]
        │     └─ LLM 注入 skill_guide 到 prompt
        ├─ [Executor.execute_units]
        │     ├─ [Scheduler.topological_sort] → 排序 Units
        │     ├─ [Planner.plan_unit] (L2) → List[Step]
        │     ├─ [Executor._run_agentic_loop] (L3)
        │     │     └─ LLM + Tools 互動
        │     └─ [Scheduler.apply_pruning] → 剪枝
        ├─ [Tracer.log_task] → task_trace.jsonl
        └─ [Responder.integrate]
               └─ 呼叫 LLM 整合結果
```

---

## 七、模型使用一覽

| 場景 | 模型 | Temperature | Max Tokens | Think |
|------|------|-------------|------------|-------|
| Intent 分流 | ROUTER_MODEL_NAME (qwen3.5:2b) | 0.0 | 8192 | False |
| RAG 必要判斷 | ROUTER_MODEL_NAME (qwen3.5:2b) | 0.0 | 8192 | False |
| 意圖解析 | MEDIUM_MODEL_NAME (qwen3.5:9b) | 0.1 | 500 | False |
| 任務拆解 (L1) | LARGE_MODEL_NAME (qwen3.6:35b) | 0.0 | 32768 | True |
| 步驟規劃 (L2) | LARGE_MODEL_NAME (qwen3.6:35b) | 0.0 | 16384 | False |
| 步驟執行 (L3) | MEDIUM_MODEL_NAME (qwen3.5:9b) | 0.0 | 8192 | False |
| 結果整合 | MEDIUM_MODEL_NAME (qwen3.5:9b) | 0.3 | 8192 | False |
| 直接回覆 | MEDIUM_MODEL_NAME (qwen3.5:9b) | 0.7 | 8192 | False |
| 對話摘要 | MEDIUM_MODEL_NAME (qwen3.5:9b) | 0.2 | 8192 | False |
| 優化器 | LARGE_MODEL_NAME (qwen3.6:35b) | 0.0 | 未限制 | False |

---

*文件版本：v1.0*
*最後更新：2026-05-21*
