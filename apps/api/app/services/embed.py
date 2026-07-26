import io
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from typing import Any

import numpy as np
import numpy.typing as npt
import open_clip
import torch
from PIL import Image

Embeddings = npt.NDArray[np.float32]

EMBEDDING_DIM = 1024
ENHANCE_TIMEOUT = float(os.getenv("ENHANCE_TIMEOUT", "5"))
ENHANCE_MAX_WORKERS = int(os.getenv("ENHANCE_MAX_WORKERS", "8"))
ENHANCE_CACHE_SIZE = 512

_device = "cuda" if torch.cuda.is_available() else "cpu"
_model = None
_tokenizer = None
_preprocess = None
_model_lock = threading.Lock()


def _load_model() -> tuple[Any, Any, Any]:
    """Lazy-load the CLIP model. Guarded because request threads race here and
    loading ViT-H-14 twice costs several GB."""
    global _model, _tokenizer, _preprocess
    if _model is None:
        with _model_lock:
            if _model is None:
                model, _, preprocess = open_clip.create_model_and_transforms(
                    "ViT-H-14", pretrained="dfn5b"
                )
                _tokenizer = open_clip.get_tokenizer("ViT-H-14")
                _preprocess = preprocess
                _model = model.to(_device).eval()
    return _model, _tokenizer, _preprocess


def warmup() -> None:
    """Load the model up front so the first request does not pay for it."""
    _load_model()


def _to_numpy(features: Any) -> Embeddings:
    array: Embeddings = features.cpu().numpy().astype(np.float32)
    return array


def embed_text(texts: list[str]) -> Embeddings:
    """Encode a batch of texts in a single forward pass."""
    if not texts:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
    model, tokenizer, _ = _load_model()
    tokens = tokenizer(texts).to(_device)
    with torch.no_grad():
        features = model.encode_text(tokens)
        features = features / features.norm(dim=-1, keepdim=True)
    return _to_numpy(features)


def embed_image(image_bytes: bytes) -> Embeddings:
    model, _, preprocess = _load_model()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    batch = preprocess(img).unsqueeze(0).to(_device)
    with torch.no_grad():
        features = model.encode_image(batch)
        features = features / features.norm(dim=-1, keepdim=True)
    vector: Embeddings = _to_numpy(features)[0]
    return vector


def embed_images(images: list[bytes]) -> Embeddings:
    """Encode a batch of images in a single forward pass."""
    if not images:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
    model, _, preprocess = _load_model()
    tensors = [preprocess(Image.open(io.BytesIO(b)).convert("RGB")) for b in images]
    batch = torch.stack(tensors).to(_device)
    with torch.no_grad():
        features = model.encode_image(batch)
        features = features / features.norm(dim=-1, keepdim=True)
    return _to_numpy(features)


_client = None
_client_lock = threading.Lock()
_enhance_cache: dict[str, str] = {}
_enhance_cache_lock = threading.Lock()


def _get_openai_client() -> Any | None:
    global _client
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None
    if _client is None:
        with _client_lock:
            if _client is None:
                from openai import OpenAI

                _client = OpenAI(api_key=api_key)
    return _client


def enhance_query(raw_query: str) -> str:
    """Translate/rephrase a query for CLIP. Falls back to the raw query on any
    failure; only successful rewrites are cached so a transient outage does not
    poison the cache."""
    if not raw_query:
        return raw_query
    with _enhance_cache_lock:
        cached = _enhance_cache.get(raw_query)
    if cached is not None:
        return cached

    client = _get_openai_client()
    if client is None:
        return raw_query
    try:
        resp = client.responses.create(
            model="gpt-4.1-nano",
            input=(
                "Translate to English if needed, then rephrase as a descriptive "
                f"scene sentence: {raw_query}"
            ),
            timeout=ENHANCE_TIMEOUT,
        )
        enhanced: str = resp.output_text
    except Exception:
        return raw_query
    if not enhanced:
        return raw_query

    with _enhance_cache_lock:
        if len(_enhance_cache) >= ENHANCE_CACHE_SIZE:
            _enhance_cache.clear()
        _enhance_cache[raw_query] = enhanced
    return enhanced


def enhance_queries(raw_queries: list[str]) -> list[str]:
    """Enhance several queries concurrently. The work is network-bound, so the
    GIL is released while waiting and N queries cost roughly one round-trip."""
    if not raw_queries:
        return []
    if len(raw_queries) == 1:
        return [enhance_query(raw_queries[0])]
    workers = min(ENHANCE_MAX_WORKERS, len(raw_queries))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(enhance_query, raw_queries))
