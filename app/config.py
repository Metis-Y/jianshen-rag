"""集中配置：优先读项目根目录 .env（见 .env.example），其次系统环境变量。"""
import os

from dotenv import load_dotenv

load_dotenv()  # 加载项目根目录的 .env（见 .env.example），不存在则跳过

# 安全
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"
JWT_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "72"))

# 模型：embedding 与 chat 各自独立配置，支持跨平台混搭
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")   # 默认凭证（两个平台未单独配时用它）

EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", SILICONFLOW_API_KEY)
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

CHAT_API_KEY = os.getenv("CHAT_API_KEY", SILICONFLOW_API_KEY)
CHAT_BASE_URL = os.getenv("CHAT_BASE_URL", "https://api.siliconflow.cn/v1")
CHAT_MODEL = os.getenv("CHAT_MODEL", "deepseek-ai/DeepSeek-V3")

# 重排：粗召回候选后用 rerank 模型精排（key 缺省复用 SILICONFLOW_API_KEY）
RERANK_API_KEY = os.getenv("RERANK_API_KEY", SILICONFLOW_API_KEY)
RERANK_BASE_URL = os.getenv("RERANK_BASE_URL", "https://api.siliconflow.cn/v1")
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

# 检索/切分 超参
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "80"))
TOPK = int(os.getenv("TOPK", "5"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))

# 存储
DATA_DIR = os.getenv("DATA_DIR", "./data")
SQLITE_PATH = os.getenv("SQLITE_PATH", "./data/jianshen.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")