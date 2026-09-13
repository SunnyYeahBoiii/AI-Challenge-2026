import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.config import Config

logger = logging.getLogger(__name__)

ENHANCE_MAX_WORKERS = Config.ENHANCE_MAX_WORKERS
ENHANCE_CACHE_SIZE = 512

_enhance_cache: dict[str, str] = {}
_enhance_cache_lock = threading.Lock()


def _gemini_translate(raw_query: str, api_key: str) -> str:
    model = quote(Config.GEMINI_MODEL, safe="")
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(
            {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": (
                                    "Translate to English if needed, then rewrite this query as one "
                                    "descriptive visual scene sentence for image retrieval. Return only "
                                    f"the rewritten sentence.\n\nQuery: {raw_query}"
                                )
                            }
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 128},
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urlopen(request, timeout=Config.GEMINI_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        return ""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    candidate = candidates[0]
    if not isinstance(candidate, dict):
        return ""
    content = candidate.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    return "".join(
        text
        for part in parts
        if isinstance(part, dict) and isinstance((text := part.get("text")), str)
    ).strip()


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

    api_key = Config.GEMINI_API_KEY.strip()
    if not api_key:
        return raw_query
    try:
        enhanced = _gemini_translate(raw_query, api_key)
    except Exception:
        logger.warning("Gemini enhance failed for %r", raw_query[:80], exc_info=True)
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
