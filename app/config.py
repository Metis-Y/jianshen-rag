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
# 思考开关（推理系模型如小米 MiMo v2.6 系列：enabled/disabled，服务端默认思考）
# 留空 = 不传该参数、走服务端默认；注意 MiMo 思考模式下 temperature 会被忽略
CHAT_THINKING = os.getenv("CHAT_THINKING", "").strip()
# Agent 模式：on = 工具调用问答（模型自选工具），off = 固定管道（检索→聚合→生成）
AGENT_MODE = os.getenv("AGENT_MODE", "on").strip().lower() != "off"

# 重排：粗召回候选后用 rerank 模型精排（key 缺省复用 SILICONFLOW_API_KEY）
RERANK_API_KEY = os.getenv("RERANK_API_KEY", SILICONFLOW_API_KEY)
RERANK_BASE_URL = os.getenv("RERANK_BASE_URL", "https://api.siliconflow.cn/v1")
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

# 检索/切分 超参
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "80"))
TOPK = int(os.getenv("TOPK", "5"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))

# 模型调用超时（秒）：embedding / chat 客户端显式超时，上游无响应时快速失败而非长时间挂起
EMBEDDING_TIMEOUT = float(os.getenv("EMBEDDING_TIMEOUT", "60"))
CHAT_TIMEOUT = float(os.getenv("CHAT_TIMEOUT", "60"))

# 存储
DATA_DIR = os.getenv("DATA_DIR", "./data")
SQLITE_PATH = os.getenv("SQLITE_PATH", "./data/jianshen.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./data/uploads")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")