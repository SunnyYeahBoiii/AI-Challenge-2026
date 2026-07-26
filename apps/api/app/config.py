import os
from dotenv import load_dotenv

load_dotenv()

# The checkpoint that built the Milvus index. Re-encoding a stored keyframe with
# it reproduces the vector in clip-embeddings-batch*-aic25.npy at cosine 1.0000;
# `ViT-H-14`/`dfn5b` (224px) only reaches 0.92, which silently degrades every
# search. Query-time encoding (app/services/embed.py) and ingestion must agree.
MODEL_ID = os.getenv("CLIP_MODEL_ID", "hf-hub:apple/DFN5B-CLIP-ViT-H-14-384")


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

    DRES_URL = os.getenv("DRES_URL", "")
    DRES_USERNAME = os.getenv("DRES_USERNAME", "")
    DRES_PASSWORD = os.getenv("DRES_PASSWORD", "")
