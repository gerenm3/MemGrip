# MemGrip Configuration
 
# --- Model ---
MODEL_BASE_URL = "http://localhost:11434"   # Ollama default
ROUTER_MODEL_NAME = ""
MEDIUM_MODEL_NAME = ""
LARGE_MODEL_NAME = "qwen3.5:35b-a3b"     
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
RERANKER_MODEL_NAME = ""         
TEMPERATURE = 0.7
ROUTE_TEMPERATURE = 0.0
SUMMARY_TEMPERATURE = 0.2
MAX_TOKENS = 2048
ROUTE_MAX_TOKENS = 50
CONFIDENCE_THRESHOLD = 0.8
SIMILARITY_THRESHOLD = 0.6
TEMP_CACHE_PATH = "./temp_cache"
TRACE_LOG_PATH = "./log"
THINK = False

# --- Memory ---
BUFFER_MAX_TOKENS = 800                     # Max tokens in short-term buffer

#mpt overflow
SUMMARY_MAX_TOKENS = 1024                    # Max tokens for rolling summary
CHROMA_DB_PATH = "./chroma_db"              # ChromaDB persistence path
COLLECTION_SUMMARY_NAME = "SUMMARY"
COLLECTION_RAW_NAME = "RAW"
IMPORTANCE_THRESHOLD = 0.5                  # Min importance score to store in vector DB
 
# --- Tools ---
ENABLE_WEB_SEARCH = True
ENABLE_FILE_RW = True
ENABLE_TASK_MANAGER = True
FILE_RW_BASE_PATH = "./workspace"          # Base directory for file read/write
PATTENRS_PATH = "./patterns.json"

# --- System Prompt ---
SYSTEM_PROMPT = """You are MemGrip, a conversational agent with persistent memory.
You can recall past conversations, manage tasks, search the web, and read/write files.
Always reason carefully before calling tools."""
SUMMARY_PROMPT = """The [CONVERSATION] is merged with the [OLD SUMMARY] to form a new summary.
with priority given to retaining information related to the user and assistant
Only the merged summary is output. """
IMPORTANCE_PROMPT = """This summary assesses the correlation between user-related information and assistant-related information,
 and outputs only floating-point score in the range of 0-1."""
ROUTE_PROMPT = """"""