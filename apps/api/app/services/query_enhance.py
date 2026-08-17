import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.config import Config

logger = logging.getLogger(__name__)

ENHANCE_TIMEOUT = Config.ENHANCE_TIMEOUT
ENHANCE_MAX_WORKERS = Config.ENHANCE_MAX_WORKERS
ENHANCE_CACHE_SIZE = 512

_client = None
_client_lock = threading.Lock()
_enhance_cache: dict[str, str] = {}
_enhance_cache_lock = threading.Lock()


def _get_openai_client() -> Any | None:
    global _client
    api_key = Config.OPENAI_API_KEY
    if not api_key:
        return None
    if _client is None:
        with _client_lock:
            if _client is None:
                from openai import OpenAI

                _client = OpenAI(api_key=api_key)
    return _client


def enhance_query(raw_query: str) -> str:
    """Translate/rephrase a query for CLIP-family encoders. Falls back to the
    raw query on any failure; only successful rewrites are cached so a
    transient outage does not poison the cache."""
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
        logger.warning("OpenAI enhance failed for %r", raw_query[:80], exc_info=True)
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
