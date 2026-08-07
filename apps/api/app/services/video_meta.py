"""In-memory video metadata cache backed by data/media-info/*.json.

The ES index `video_texts` stores frame-level documents (ocr_text/asr_text) and
carries no video metadata, so enriching search hits from ES cost one round-trip
per unique video and returned empty strings. The metadata actually lives on disk
as one JSON file per video, small enough to hold in memory for the whole process.
"""

import json
import threading
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve()
MEDIA_DIR = next(
    (p / "data" / "media-info" for p in [_BASE, *_BASE.parents] if (p / "data" / "media-info").exists()),
    _BASE,
)

_META: dict[str, dict[str, Any]] = {}
_loaded = False
_lock = threading.Lock()

_EMPTY: dict[str, Any] = {}


def _read_one(path: Path) -> tuple[str, dict[str, Any]] | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return path.stem, {
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "keywords": data.get("keywords", []) or [],
        "watch_url": data.get("watch_url", ""),
        "author": data.get("author", ""),
        "channel_id": data.get("channel_id", ""),
        "length": data.get("length", 0) or 0,
        "publish_date": data.get("publish_date", ""),
    }


def load(media_dir: Path | None = None) -> int:
    """Load every media-info JSON into memory. Idempotent, safe to call twice."""
    global _loaded
    directory = media_dir or MEDIA_DIR
    with _lock:
        if _loaded and media_dir is None:
            return len(_META)
        meta: dict[str, dict[str, Any]] = {}
        if directory.exists():
            for path in directory.glob("*.json"):
                entry = _read_one(path)
                if entry:
                    meta[entry[0]] = entry[1]
        _META.clear()
        _META.update(meta)
        _loaded = True
        return len(_META)


def get(video_id: str) -> dict[str, Any]:
    """O(1) metadata lookup. Loads lazily if startup warmup never ran."""
    if not _loaded:
        load()
    return _META.get(video_id, _EMPTY)


def count() -> int:
    return len(_META)
