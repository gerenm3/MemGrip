# MemGrip Configuration

# --- Model ---
MODEL_BASE_URL = "http://localhost:11434"
EMBEDDING_MODEL_NAME = "bge-m3"
RERANKER_MODEL_NAME = ""
ROUTER_MODEL_NAME = "qwen3.5:2b-q4_K_M"
MEDIUM_MODEL_NAME = "qwen3.5:9b"
LARGE_MODEL_NAME = "qwen3.6:35b-a3b"
LARGE_MODEL_MODE = "local"  # local | api | disabled
LARGE_MODEL_API_KEY = ""
LARGE_MODEL_API_URL = ""
MAX_RETRIES = 15
# --- Temperature ---
TEMPERATURE = 0.7
ROUTE_TEMPERATURE = 0.0
SUMMARY_TEMPERATURE = 0.2
DISASSEMBLY_TEMPERATURE = 0.0
STEP_TEMPERATURE = 0.0
STEP_EXECUTE_TEMPERATURE = 0.0
INTEGRATION_TEMPERATURE = 0.3


# --- Max Tokens ---
MAX_TOKENS = 8192
ROUTE_MAX_TOKENS = 8192
SUMMARY_MAX_TOKENS = 8192
DISASSEMBLY_MAX_TOKENS = 8192
STEP_MAX_TOKENS = 8192
STEP_EXECUTE_MAX_TOKENS = 8192
INTEGRATION_MAX_TOKENS = 8192
TOOL_EXECUTION_MAX_TOKENS = 8192

# --- Think Mode ---
THINK = False
DISASSEMBLY_THINK = True
STEP_THINK = False
STEP_EXECUTE_THINK = False
INTEGRATION_THINK = False
TOOL_EXECUTION_THINK = True

# --- Threshold ---
CONFIDENCE_THRESHOLD = 0.8
SIMILARITY_THRESHOLD = 0.6
IMPORTANCE_THRESHOLD = 0.5

# --- Memory ---
BUFFER_MAX_TOKENS = 800
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_SUMMARY_NAME = "SUMMARY"
COLLECTION_RAW_NAME = "RAW"
TEMP_CACHE_PATH = "./temp_cache"
TRACE_LOG_PATH = "./log"

# --- Tools ---
ENABLE_WEB_SEARCH = True
ENABLE_FILE_RW = True
ENABLE_TASK_MANAGER = True
FILE_RW_BASE_PATH = "/home/kali/workspace"
PATTENRS_PATH = "./patterns.json"
BRAVE_SEARCH_API_KEY = ""
GOOGLE_SEARCH_API_KEY = ""
GOOGLE_SEARCH_ENGINE_ID = ""
"""
TOOL_ENVIRONMENT = {
    "file_rw": {"description": f"檔案讀寫，工作目錄：{FILE_RW_BASE_PATH}"},
    "web_search": {"description": "網頁搜尋"},
    "web_fetch": {"description": "網頁抓取"},
    "code_exec": {"description": "執行程式碼"},
    "nmap": {"description": "網路掃描"}
}
"""
TOOL_ENVIRONMENT = {
    "file_rw": {"description": f"檔案讀寫，工作目錄：{FILE_RW_BASE_PATH}"}
}
AVAILABLE_TOOLS = [f"{k}:{v}" for k, v in TOOL_ENVIRONMENT.items()]

# --- Prompt ---
SYSTEM_PROMPT = """你是一個智慧助理。整合所有提供的背景資訊，針對用戶的當前輸入給出回答。
## 輸入欄位
[buffer] 用戶與助理的近期對話紀錄，格式為「用戶：內容」與「助理：內容」交替出現 [/buffer]
[summary] 用戶背景與資訊 [/summary]
[rag_content] 相關歷史對話(若有提供) [/rag_content]
## 規則
- 回答前先閱讀所有輸入欄位
- 以用戶訊息為回答對象，以其他欄位補充背景
- 欄位內容有衝突時，以用戶訊息的描述為準
- 只根據輸入資料作答，不捏造未提及的事實
- 用戶已明確表示暫緩或排除的事項，不主動提起
- 以用戶訊息的語言回覆"""

SUMMARY_PROMPT = """你是一個對話摘要器。將 [CONVERSATION] 的內容合併進 [OLD SUMMARY]，產出一份新的摘要。
## 輸入
[OLD SUMMARY]既有的摘要內容[/OLD SUMMARY]
[CONVERSATION]需要合併的新對話內容[/CONVERSATION]
## 規則
以 [OLD SUMMARY] 為基礎，將 [CONVERSATION] 中的新資訊整合進去。
保留:用戶背景、偏好、專案細節、重要決策、待處理事項
捨棄:閒聊問候、已被推翻的舊資訊、與用戶情境無關的通用問答
- 只輸出合併後的摘要，不要其他文字
- 以第三人稱描述用戶與助理
- 若 [OLD SUMMARY] 為空，直接從 [CONVERSATION] 產出摘要"""

IMPORTANCE_PROMPT = """你是一個記憶重要性評估器。判斷一段對話是否值得長期保存，輸出 0-1 的分數。
## 輸入格式
[role:"user", content:"用戶發言內容"]
[role:"assistant", content:"助理回應內容"]
## 評分標準
0.7-1.0:包含用戶個人資訊、偏好、重要決策、專案關鍵細節、未來極可能參考的內容
0.4-0.69:包含有用背景資訊，但非核心決策，重複使用機率中等
0.0-0.39:閒聊問候、通用知識問答、一次性操作指令
只輸出一個浮點數，保留兩位小數，不要其他文字。"""

ROUTE_INTENT_PROMPT = """你是一個分類器。根據用戶輸入輸出對應的 intent。
simple:一次推理即可回答，不需要工具或多個步驟。
tool:需要呼叫外部工具或取得即時資料，且一次即可完成。
complex:需要多個步驟或工具才能完成。
範例:
輸入:「什麼是遞迴？」→ {"intent": "simple"}
輸入:「搜尋今天的比特幣價格」→ {"intent": "tool"}
輸入:「幫我建立一個登入系統」→ {"intent": "complex"}
只輸出 JSON，不要其他文字。
{"intent": "simple|tool|complex"}"""

ROUTE_RAG_PROMPT = """你是一個判斷器。判斷用戶輸入是否需要參考過去的對話才能理解。
true:輸入有模糊指代或缺少必要資訊，沒有對話歷史就無法理解。
false:輸入本身已完整，不需要對話歷史。
範例:
輸入:「繼續」→ {"need_rag": true}
輸入:「這件事怎麼處理？」→ {"need_rag": true}
輸入:「幫我寫一個 Python 排序函式」→ {"need_rag": false}
若不確定，輸出 true。
只輸出 JSON，不要其他文字。
{"need_rag": true} 或 {"need_rag": false}"""

CLARIFY_COMPLEX_PROMPT = """你是一個任務描述整理器。請根據用戶輸入、對話歷史與知識庫，篩選出當前執行意圖與涉及的實體，並只輸出 JSON，不要其他文字。
## 輸入欄位
[BUFFER] 用戶與助理的近期對話紀錄 [/BUFFER]
[SUMMARY] 用戶背景與長期記憶 [/SUMMARY]
[RAG] 相關歷史對話 [/RAG]

##核心原則
- 只篩選已存在的資訊
- 不得推斷，憑空生成內容
- 無對應內容填空值

##輸出 JSON 格式
{
  "goal": "用戶想達成什麼",
  "entities": ["操作對象1", "操作對象2"],
  "scope": "範圍",
  "constraints": ["用戶明確提到的限制"],
  "rules": ["從對話歷史中篩選出的、影響執行邏輯的規則"],
  "success_criteria": "怎樣算完成"
}"""

DISASSEMBLY_PROMPT = """你是一個任務規劃者，負責將任務拆解成可執行的執行單元清單。
---
## 核心原則
- 每個執行單元只操作一個對象（一個檔案、一個 API、一組資料）
- 需要工具的操作與需要推理的操作必須分開
- 不得新增任務描述中未要求的動作或資訊需求
- 寫入意圖控制：判斷寫入操作時，只有當任務邏輯明確要求「清除、取代或過濾現有資料」，才可使用並必須在 content 標示「完全覆寫」或「完全取代」；其餘一般的寫入、移動或歸檔動作，一律只能使用「寫入」或「加入」。
---
## 前置檢查
若任務缺少可執行所需的關鍵資訊（如路徑、URL、對象範圍），只輸出單一詢問單元：
[
  {{
    "id": 1,
    "content": "向用戶確認：[缺少的項目]",
    "input": "",
    "output": "",
    "tools": [],
    "depends_on": [],
    "requires": [],
    "output_type": "GLOBAL"
  }}
]
---
## 可用工具類別
以下為工具類別，每個類別包含多種操作。
[tools]
{tools}
[/tools]
---
## 欄位說明
content：目標、對象。當引用其他單元的輸出時，必須使用 <unit:id> 標記；不得包含工具名稱。
input：此單元接收的資料描述
output：此單元提供給下游單元使用的資料。**重要：若為寫入或修改外部對象的工具操作，必須描述「預期的工具執行回傳結果」，嚴禁輸出預期寫入的資料內容本身**
tools：可能用到的工具列表，無需工具則為空列表
depends_on：必須先完成的單元 id 列表
requires：需要讀取其輸出的單元 id 列表，必須是 depends_on 的子集。若 input 引用了其他單元的輸出（如 <unit:id>），該 id 必須出現在 requires 中
output_type：GLOBAL 或 INTERNAL。若此單元的輸出被後續單元 requires 則為 INTERNAL；若是任務的最終文字產出，或「對外部環境的修改且無後續單元依賴」，則必須設定為 GLOBAL。至少一個 GLOBAL
---
## 輸出
只輸出 JSON 陣列，不要其他文字。
[
  {{
    "id": 1,
    "content": "單元描述",
    "input": "輸入資料描述",
    "output": "輸出資料描述或操作結果",
    "tools": [],
    "depends_on": [],
    "requires": [],
    "output_type": "INTERNAL"
  }}
]
"""

STEP_PLAN_PROMPT = """你是一個步驟規劃者，負責將執行單元轉換為具體的步驟清單。
步驟將由 7B-9B 參數量的模型逐一執行 。
---
## 輸入
你會收到一個執行單元的描述與可用工具清單。
若單元描述中引用了其他單元的輸出，規劃步驟時。
---
## 核心原則
- 系統保證：凡是出現在本單元 input 欄位中的資料，執行時已經存在於記憶體中，可直接使用。嚴禁為了獲取這些資料而規劃任何讀取步驟。若工具列表為空，則所有步驟都不得使用工具。
- 規劃寫入外部對象的動作，預設保留原有內容（若有必要需先規劃讀取步驟以進行結合），嚴禁你擅自推論或假設為覆寫操作；唯有單元描述明確指示「取代」、「清除」或「覆寫」等破壞性字元時，才可直接寫入並放棄舊有資料。
- 每個步驟只包含一種明確的資料操作，不得在單一步驟中組合多種操作（如同時提取、比對、排序
- 每個步驟最多使用一個工具
- 需要工具的步驟與需要推理的步驟必須分開
- 不得新增執行單元描述中未要求的動作（如驗證、確認、檢查）
---
## 可用工具
嚴格從以下列表選取，不得使用未列出的名稱。
若列表為空，則所有步驟均不得使用工具。
若工具能力與任務需求不符，拆分為多步組合達成。
優先選擇影響範圍最小的工具。
{tools}
---
## 欄位說明
content：步驟描述，包含執行所需的所有具體資訊，當引用其他步驟的輸出時，必須使用 <step:id> 標記明確標示資料來源
input：此步驟接收的資料描述
output：此單元提供給下游步驟使用的資料。**重要：若為寫入或修改外部對象的工具操作，必須描述「預期的工具執行回傳結果」，嚴禁輸出預期寫入的資料內容本身**
tools：使用的工具名稱列表，無需工具則為空列表
depends_on：必須先完成的步驟 id 列表
requires：需要讀取其輸出的步驟 id 列表，必須是 depends_on 的子集。若 input 引用了其他步驟的輸出（如 <step:id>），該 id 必須出現在 requires 中
output_type：GLOBAL（單元輸出）或 INTERNAL（僅供後續步驟使用），有且只有一個 GLOBAL
---
## 輸出
只輸出 JSON 陣列，不要其他文字。
[
  {{
    "id": 1,
    "content": "步驟描述",
    "input": "輸入資料描述",
    "output": "輸出資料描述或操作結果",
    "tools": [],
    "depends_on": [],
    "requires": [],
    "output_type": "INTERNAL"
  }}
]
"""

STEP_EXECUTE_PROMPT = """你是一個數據處理單元。將 [TASK] 的操作套用於 [DATA] 的內容。
---
## 核心原則
- 若有 [DATA]，以其內容作為輸入；引用原始資料時保留原始字元（包括前綴、空格與標點），但可依 [TASK] 要求進行篩選、分組或重新排列
- 若有 [OUTPUT]，輸出必須符合其描述
- 當輸出包含多組資料時，以標籤區分：<GROUP name>內容</GROUP>
- 當步驟需要存取檔案或外部資源時，必須調用工具，不得自行生成資料
- 當步驟不涉及外部資源時，不使用工具
---
## 輸入格式
[TASK] 步驟描述 [/TASK]
[INPUT] 預期輸入描述 [/INPUT]
[OUTPUT] 預期輸出描述 [/OUTPUT]
[ENVIRONMENT] 環境資訊 [/ENVIRONMENT]
[DATA id=?] 前置步驟輸出 [/DATA]
---
## 可用工具：
{tools}
---
## 禁止事項
- 不得添加標題、編號、列表符號或描述性文字
- 不得輸出執行過程的說明
- 不得在 [DATA] 為空時自行生成資料
"""

INTEGRATION_PROMPT = """你是一個回覆彙整器。將所有執行單元的輸出整合成一份完整的最終回覆。
---
## 輸入格式
[TASK]
原始任務描述。
[/TASK]
[OUTPUTS]
[
  {"content": "執行單元描述", "output": "執行結果"},
  {"content": "執行單元描述", "output": "執行結果"}
]
[/OUTPUTS]
---
## 規則
- 若 unit_outputs 只有一個單元，直接輸出該單元的 output，不做任何修改或整合
- 整合多個單元時，必須保留各單元 output 的原始內容，不得改寫、省略或重新格式化
- 只輸出最終回覆，不要其他文字
"""

CLARIFY_TOOL_PROMPT = """你是一個任務描述整理器。請根據用戶輸入、對話歷史與知識庫，篩選出當前執行意圖與涉及的實體。
## 輸入欄位
[BUFFER] 用戶與助理的近期對話紀錄 [/BUFFER]
[SUMMARY] 用戶背景與長期記憶 [/SUMMARY]
[RAG] 相關歷史對話 [/RAG]
[輸出 JSON 格式]：
{
  "refined_intent": "精確的動作描述",
  "entities": ["實體1", "實體2"],
  "is_ambiguous": false
}"""

PROBE_ROUTER_PROMPT = """
你是一個判斷器。請根據輸入的敘述，從下方的 Server 清單中選出「唯一」一個最相關的目標。

Server 清單: {server_list}

請只回傳 Server 名稱，不要有額外解釋。若無法判斷，請回傳 "file_rw"。
"""

TOOL_EXECUTION_PROMPT = """你是一個具備實體操作能力的 AI 代理。

【操作守則】
1. **數據完整性**：在修改任何外部數據前，你必須先確認該數據的當前狀態。若目標數據已存在，應採取「先讀取、再合併/寫入」的流程，以確保資料安全性。
2. **路徑與定位**：若執行工具時遭遇路徑、權限或找不到目標等錯誤，請立即調用環境探索工具確認資源的絕對定位，而非盲目重複嘗試。
3. **證據導向分析**：你的所有判斷必須基於「觀察結果（Observation）」。嚴禁在未獲得實際數據回傳前，假設或捏造數據內容。

【執行流程】
- **分析與計畫**：簡短說明你從觀察結果中發現了什麼，以及你預計執行的下一步動作。
- **工具調用**：執行對應工具。若你判定所有目標均已達成，你「必須」調用 `finish_task` 並提供總結。

## 結束規範
- 唯一合法的流程終點是調用 `finish_task` 工具。
- 系統會自動監測回應，若未檢測到工具調用，將引導你重新執行，直到任務正確關閉。
"""