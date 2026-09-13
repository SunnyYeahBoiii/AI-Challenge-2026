import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = API_DIR if (API_DIR / "data").exists() else API_DIR.parents[1]
DEFAULT_OBJECT_DETECTIONS_PATH = (PROJECT_DIR / "data" / "objects" / "object_detections.parquet")
WEIGHTS_DIR = API_DIR / "weights"
DEFAULT_KEYFRAMES_DIR = PROJECT_DIR / "data" / "keyframes" / "keyframes"
DEFAULT_VIDEOS_DIR = PROJECT_DIR / "data" / "video"


class Config:
    MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
    MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
    MILVUS_SEARCH_EF = int(os.getenv("MILVUS_SEARCH_EF", "128"))
    ES_URL = os.getenv("ES_URL", "http://localhost:9200")
    ES_USER = os.getenv("ES_USER", "")
    ES_PASS = os.getenv("ES_PASS", "")
    ES_MAX_KEYWORD_HITS = int(os.getenv("ES_MAX_KEYWORD_HITS", "10000"))
    # ASR keywords phrase-match: 0 keeps order and adjacency exact. Raise it only
    # if transcript filler words start swallowing otherwise-correct phrases.
    ES_ASR_PHRASE_SLOP = int(os.getenv("ES_ASR_PHRASE_SLOP", "0"))
    # Reciprocal Rank Fusion: score = w / (RRF_K + rank), summed per source.
    RRF_K = int(os.getenv("RRF_K", "60"))
    RRF_VECTOR_WEIGHT = float(os.getenv("RRF_VECTOR_WEIGHT", "1.0"))
    RRF_TEXT_WEIGHT = float(os.getenv("RRF_TEXT_WEIGHT", "1.0"))
    # Collapse consecutive near-duplicate keyframes of one shot into a single hit.
    ES_DEDUPE_BY_SHOT = os.getenv("ES_DEDUPE_BY_SHOT", "true").lower() == "true"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "5"))
    ENHANCE_MAX_WORKERS = int(os.getenv("ENHANCE_MAX_WORKERS", "8"))
    DEFAULT_TOP_K = 20
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    OBJECT_DETECTIONS_PATH = os.getenv("OBJECT_DETECTIONS_PATH", str(DEFAULT_OBJECT_DETECTIONS_PATH))

    DRES_URL = os.getenv("DRES_URL", "")

    # MinIO/S3 storage for keyframes + videos. ENDPOINT is host[:port] only, no
    # scheme — swap it (and MINIO_SECURE) between practice (public domain, https)
    # and competition (Tailscale IP, plain http) via .env, no code change needed.
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_SECURE = os.getenv("MINIO_SECURE", "true").lower() == "true"
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
    MINIO_BUCKET_KEYFRAMES = os.getenv("MINIO_BUCKET_KEYFRAMES", "keyframes")
    MINIO_BUCKET_VIDEOS = os.getenv("MINIO_BUCKET_VIDEOS", "videos")

    # Keyframes and source videos are served from local disk.
    KEYFRAMES_DIR = os.getenv("KEYFRAMES_DIR", str(DEFAULT_KEYFRAMES_DIR))
    VIDEOS_DIR = os.getenv("VIDEOS_DIR", str(DEFAULT_VIDEOS_DIR))
