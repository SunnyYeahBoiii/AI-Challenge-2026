import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = API_DIR if (API_DIR / "data").exists() else API_DIR.parents[1]
DEFAULT_OBJECT_DETECTIONS_PATH = (PROJECT_DIR / "data" / "objects" / "object_detections.parquet")
WEIGHTS_DIR = API_DIR / "weights"
DEFAULT_KEYFRAMES_DIR = PROJECT_DIR / "data" / "keyframes"


class Config:
    MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
    MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
    MILVUS_SEARCH_EF = int(os.getenv("MILVUS_SEARCH_EF", "128"))
    ES_URL = os.getenv("ES_URL", "http://localhost:9200")
    ES_USER = os.getenv("ES_USER", "")
    ES_PASS = os.getenv("ES_PASS", "")
    ES_MAX_KEYWORD_HITS = int(os.getenv("ES_MAX_KEYWORD_HITS", "10000"))
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ENHANCE_TIMEOUT = float(os.getenv("ENHANCE_TIMEOUT", "5"))
    ENHANCE_MAX_WORKERS = int(os.getenv("ENHANCE_MAX_WORKERS", "8"))
    DEFAULT_TOP_K = 20
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    OBJECT_DETECTIONS_PATH = os.getenv("OBJECT_DETECTIONS_PATH", str(DEFAULT_OBJECT_DETECTIONS_PATH))

    DRES_URL = os.getenv("DRES_URL", "")

    # CloudFront is the only public origin for HLS videos. It maps /videos/* to
    # the S3 bucket, so callers never receive an S3 URL or AWS credentials.
    MEDIA_BASE_URL = os.getenv(
        "MEDIA_BASE_URL", "https://d76fwc0pqjf9a.cloudfront.net"
    ).rstrip("/")

    # Public MinIO origin used as an HLS fallback. Credentials remain server-only;
    # clients receive only public playlist URLs.
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "").strip().rstrip("/")
    MINIO_SECURE = os.getenv("MINIO_SECURE", "true").lower() == "true"
    MINIO_BUCKET_VIDEOS = os.getenv("MINIO_BUCKET_VIDEOS", "videos").strip()

    # Keyframes are served from local disk via the API.
    KEYFRAMES_DIR = os.getenv("KEYFRAMES_DIR", str(DEFAULT_KEYFRAMES_DIR))
