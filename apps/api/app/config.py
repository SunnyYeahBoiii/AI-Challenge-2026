import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    MILVUS_URI = os.getenv("MILVUS_URI", "")
    MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
    ES_URL = os.getenv("ES_URL", "")
    ES_USER = os.getenv("ES_USER", "")
    ES_PASS = os.getenv("ES_PASS", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ENSEMBLE_CONFIG_PATH = os.getenv("ENSEMBLE_CONFIG_PATH", "config/ensemble.json")
    ENSEMBLE_RRF_K = int(os.getenv("ENSEMBLE_RRF_K", "60"))
    ENSEMBLE_CANDIDATE_TOP_K = int(os.getenv("ENSEMBLE_CANDIDATE_TOP_K", "200"))
    TEXT_EMBEDDING_CACHE_SIZE = int(os.getenv("TEXT_EMBEDDING_CACHE_SIZE", "512"))
    DRES_BASE_URL = os.getenv("DRES_BASE_URL", "").rstrip("/")
    DRES_EVALUATION_ID = os.getenv("DRES_EVALUATION_ID", "")
    DRES_SESSION_TOKEN = os.getenv("DRES_SESSION_TOKEN", "")
    DRES_TIMEOUT_SECONDS = float(os.getenv("DRES_TIMEOUT_SECONDS", "10"))
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    EMBEDDING_DIM = 1024
    MODEL_ID = "hf-hub:apple/DFN5B-CLIP-ViT-H-14-384"
    DEFAULT_TOP_K = 20
    MAX_TOP_K = 100
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
