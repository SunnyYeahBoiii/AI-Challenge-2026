import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = API_DIR if (API_DIR / "data").exists() else API_DIR.parents[1]
DEFAULT_OBJECT_DETECTIONS_PATH = (PROJECT_DIR / "data" / "objects" / "object_detections.parquet")
WEIGHTS_DIR = API_DIR / "weights"


class Config:
    MILVUS_URI = os.getenv("MILVUS_URI", "")
    MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
    ES_URL = os.getenv("ES_URL", "")
    ES_USER = os.getenv("ES_USER", "")
    ES_PASS = os.getenv("ES_PASS", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    DEFAULT_TOP_K = 20
    MAX_TOP_K = 100
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
