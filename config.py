# MemGrip Configuration
 
# --- Model ---
MODEL_BASE_URL = "http://localhost:11434"   # Ollama default
MODEL_NAME = "qwen3.5:35b-a3b"              
TEMPERATURE = 0.7
MAX_TOKENS = 2048
 
# --- Memory ---
BUFFER_SIZE = 4                             # Max turns in short-term buffer
SUMMARY_MAX_TOKENS = 512                    # Max tokens for rolling summary
CHROMA_DB_PATH = "./chroma_db"             # ChromaDB persistence path
COLLECTION_NAME = "memgrip"
IMPORTANCE_THRESHOLD = 0.5                  # Min importance score to store in vector DB
 
# --- Embeddings ---
EMBEDDING_MODEL = "BAAI/bge-m3"   # e.g. BAAI/bge-m3
 
# --- Tools ---
ENABLE_WEB_SEARCH = True
ENABLE_FILE_RW = True
ENABLE_TASK_MANAGER = True
FILE_RW_BASE_PATH = "./workspace"          # Base directory for file read/write
 
# --- System Prompt ---
SYSTEM_PROMPT = """You are MemGrip, a conversational agent with persistent memory.
You can recall past conversations, manage tasks, search the web, and read/write files.
Always reason carefully before calling tools."""