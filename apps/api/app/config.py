import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# The checkpoint that built the Milvus index. Re-encoding a stored keyframe with
# it reproduces the vector in clip-embeddings-batch*-aic25.npy at cosine 1.0000;
# `ViT-H-14`/`dfn5b` (224px) only reaches 0.92, which silently degrades every
# search. Query-time encoding (app/services/embed.py) and ingestion must agree.
MODEL_ID = os.getenv("CLIP_MODEL_ID", "hf-hub:apple/DFN5B-CLIP-ViT-H-14-384")
API_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = API_DIR if (API_DIR / "data").exists() else API_DIR.parents[1]
DEFAULT_OBJECT_DETECTIONS_PATH = (PROJECT_DIR / "data" / "objects" / "object_detections.parquet")


class Config:
    MILVUS_URI = os.getenv("MILVUS_URI", "")
    MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
    ES_URL = os.getenv("ES_URL", "")
    ES_USER = os.getenv("ES_USER", "")
    ES_PASS = os.getenv("ES_PASS", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    EMBEDDING_DIM = 1024
    DEFAULT_TOP_K = 20
    MAX_TOP_K = 100
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    OBJECT_DETECTIONS_PATH = os.getenv("OBJECT_DETECTIONS_PATH", str(DEFAULT_OBJECT_DETECTIONS_PATH))

    DRES_URL = os.getenv("DRES_URL", "")
