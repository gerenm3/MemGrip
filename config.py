# v2 MemGrip Configuration
# 移除了 2B/3B 模型相關參數，routing 統一使用 MEDIUM_MODEL_NAME

import os
from pathlib import Path

# --- Skill Directories ---
SKILL_DIR_BASE = Path("/home/kali/memgrip/skills")
TASK_TYPES = ["general", "software_dev", "it_security"]
VALID_INTENTS = ["simple", "tool", "complex"]

SKILL_DIMENSIONS = {
    "reasoning_resolution": {
        "name": "推論解析度 (Reasoning Resolution)",
        "range": "direct → step_by_step → chain_of_thought",
        "description": "模型思考的步長，決定推導過程的顯式程度"
    },
    "constraint_rigidity": {
        "name": "約束剛性 (Constraint Rigidity)",
        "range": "guideline → rule → hard_schema",
        "description": "模型的自由度與合規性的平衡"
    },
    "signal_noise_ratio": {
        "name": "資訊信噪比 (Signal-to-Noise Ratio)",
        "range": "minimal → balanced → rich",
        "description": "核心上下文與邊緣資訊的比例"
    },
    "boundary_anchoring": {
        "name": "邊界錨定 (Boundary Anchoring)",
        "range": "happy_path → mixed → edge_cases",
        "description": "典型案例與邊緣案例的比例"
    },
    "uncertainty_handling": {
        "name": "不確定性處置 (Uncertainty Handling)",
        "range": "aggressive → balanced → conservative",
        "description": "資訊不足時的行為模式"
    }
}

# ─── L1/L2 Skill 初始化 ───

SKILL_FORMAT_EXAMPLE = """
{
  "reasoning_resolution": {
    "core_concept": "描述推論解析度的核心概念",
    "prompt_patterns": {"pattern1": "說明", "pattern2": "說明"},
    "design_principles": ["原則1", "原則2"],
    "pitfalls": ["陷阱1", "陷阱2"]
  },
  "constraint_rigidity": {
    "core_concept": "描述約束剛性的核心概念",
    "prompt_patterns": {"pattern1": "說明"},
    "design_principles": ["原則1"],
    "pitfalls": ["陷阱1"]
  }
}"""

L1_DOMAIN_DESCRIPTIONS = {
    "global": "通用任務，不限定領域",
    "general": "日常助理任務，強調自然語言理解和使用者意圖",
    "software_dev": "程式開發任務，強調模組化和技術精確性",
    "it_security": "資安任務，強調風險控制和操作謹慎性",
}

L2_DOMAIN_DESCRIPTIONS = {
    "global": "通用任務，不限定領域",
    "general": "日常助理任務，強調直觀的工具選擇與清晰的執行順序",
    "software_dev": "程式開發任務，強調依賴關係精確性與技術可行性",
    "it_security": "資安任務，強調操作謹慎性與風險最小化",
}

L1_SKILL_DIMENSIONS = ["reasoning_resolution", "constraint_rigidity", "signal_noise_ratio", "boundary_anchoring", "uncertainty_handling"]
L2_SKILL_DIMENSIONS = L1_SKILL_DIMENSIONS

LVS_EVENT_SCORES = {
    "task_failed": 30,
    "unit_failed": 8,
    "replan": 10,
    "review_fail": 3,
    "loop_hit": 4,
}

# --- Complex Flow 參數 ---
MAX_REPLAN_ATTEMPTS = 2      # Unit 層級重新規劃上限次數
CONTEXT_SAFETY_RATIO = 0.8   # Context 安全閾值（80%）
APPROVAL_TIMEOUT = 1800      # HITL 人工批准逾時（預設 30 分鐘，單位秒）
EMBEDDING_THRESHOLD = 0.75   # Embedding 相似度閾值
MAX_CLARIFY_ROUNDS = 2       # 最多澄清輪數
CLARIFY_TIMEOUT = 20         # 每次 clarify LLM 呼叫逾時（秒）
CLARIFY_MAX_ATTEMPTS = 3     # clarify 最多嘗試次數
LLM_TIMEOUT = 120            # 一般 LLM 呼叫逾時（秒）

# --- Clarify ---
CLARIFY_TEMPERATURE = 0.1
CLARIFY_MAX_TOKENS = 500

# 統一命名規則：{用途}_MODEL_NAME
# v2 僅保留三層模型：ROUTER → MEDIUM → LARGE → EMBEDDING
ROUTER_MODEL_NAME = "qwen3.5:9b"
MEDIUM_MODEL_NAME = "qwen3.5:9b"
LARGE_MODEL_NAME = "qwen3.6:35b-a3b"
EMBEDDING_MODEL_NAME = "bge-m3"
MODEL_BASE_URL = "http://localhost:11434"

LARGE_MODEL_MODE = "local"   # local | api | disabled
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
AGENTIC_TEMPERATURE = 0.0

# --- Max Tokens ---
MAX_TOKENS = 8192
ROUTE_MAX_TOKENS = 8192
SUMMARY_MAX_TOKENS = 8192
DISASSEMBLY_MAX_TOKENS = 32768
STEP_MAX_TOKENS = 16384
STEP_EXECUTE_MAX_TOKENS = 16384
STEP_EXECUTE_MAX_ITERATIONS = 5
INTEGRATION_MAX_TOKENS = 8192
TOOL_EXECUTION_MAX_TOKENS = 8192
AGENTIC_MAX_TOKENS = 2048

# --- Think Mode ---
THINK = False
DISASSEMBLY_THINK = True
STEP_THINK = False
STEP_EXECUTE_THINK = False
INTEGRATION_THINK = False
TOOL_EXECUTION_THINK = True
AGENTIC_THINK = False

# --- Threshold ---
IMPORTANCE_HIGH = 0.7
IMPORTANCE_LOW = 0.3
SIMILARITY_UPPER_BOUNDARY = 0.7

# --- Memory ---
BUFFER_MAX_TOKENS = 800
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_SUMMARY_NAME = "SUMMARY"
COLLECTION_RAW_NAME = "RAW"
TEMP_CACHE_PATH = "./temp_cache"
TEMP_CACHE_DECAY_LAMBDA = 0.01
TEMP_CACHE_MAX_TOKENS = 50000
TEMP_CACHE_MAX_ITEMS = 100
TEMP_CACHE_IDLE_SECONDS = 900
TEMP_CACHE_FORCE_TOKENS = 8000
TEMP_CACHE_TOP_K = 10
TEMP_CACHE_EVICTION_THRESHOLD = 0.05
# --- Log Paths ---
LOGS_DIR = "logs/"
TRACE_LOG_PATH = "logs/trace.jsonl"
TASK_TRACE_PATH = "logs/task_trace.jsonl"
HEALTH_LOG_PATH = "logs/health.log"
SIGNAL_LOG_PATH = "logs/signal_log.jsonl"

# --- Debug ---
DEBUG_MODE = os.getenv("MEMGRIP_DEBUG", "0") == "1"

# --- Vector consistency ---
VECTOR_REPAIR_INTERVAL = 50

# --- Tools ---
ENABLE_WEB_SEARCH = True
ENABLE_FILE_RW = True
ENABLE_TASK_MANAGER = True
FILE_RW_BASE_PATH = "/home/kali/workspace"
PATTERNS_PATH = "./patterns.json"
BRAVE_SEARCH_API_KEY = ""
GOOGLE_SEARCH_API_KEY = ""
GOOGLE_SEARCH_ENGINE_ID = ""

# --- MCP Server ---
MCP_TIMEOUT_SECONDS = max(1, int(os.getenv("MCP_TIMEOUT_SECONDS", "30")))

# --- Base Roles (Prompt 角色注入) ---
BASE_ROLES = {
    "disassembly": "你是一個任務規劃者，負責將任務拆解成可執行的執行單元清單。",
    "step_plan": "你是一個步驟規劃者，負責將執行單元拆解為具體的執行步驟。",
    "step_execute": "你是一個執行者，負責完成指定的原子步驟。",
}
