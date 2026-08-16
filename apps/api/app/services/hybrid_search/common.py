"""Shared frame helpers: aliases, enrichment, and keyword filtering."""

import math
from collections.abc import Iterable, Sequence
from typing import Any

from app.services import video_meta
from app.services.es_client import es_client
from app.services.storage import keyframe_url, video_url

Frame = dict[str, Any]
Box = dict[str, Any]
FrameKey = tuple[Any, Any]
Vector = list[float] | None

TOPK_BUCKET_MAXIMA = (500, 1500, 5000)
FILTER_FETCH_CHUNK = 500


# ── Filter expressions ──────────────────────────────────────────────────────
def _quote(value: Any) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _video_expr(video_ids: Sequence[str]) -> str | None:
    if not video_ids:
        return None
    return f"video_id in [{', '.join(_quote(v) for v in video_ids)}]"


# ── Enrichment ──────────────────────────────────────────────────────────────
def _frame_key(frame: Frame) -> FrameKey:
    return (frame.get("video_id"), frame.get("frame_index"))


def _enrich_frames(frames: Iterable[Frame]) -> list[Frame]:
    """Attach video metadata and dedupe by (video_id, frame_index).

    Metadata comes from the in-process media-info cache; the previous ES lookup
    cost one round-trip per video and returned fields the index does not store.
    """
    seen: set[FrameKey] = set()
    deduped: list[Frame] = []
    for f in frames:
        key = _frame_key(f)
        if key in seen:
            continue
        seen.add(key)
        meta = video_meta.get(f.get("video_id", ""))
        f["title"] = meta.get("title", "")
        # Omit bulky per-video fields from every hit — they dominate JSON size at
        # large topk and the UI does not render them on result cards.
        f["description"] = ""
        f["keywords"] = []
        f["author"] = meta.get("author", "")
        f["publish_date"] = meta.get("publish_date", "")
        f["watch_url"] = f.get("youtube_url") or meta.get("watch_url", "")
        f["video_url"] = video_url(f.get("video_id", ""))
        f["thumbnail_url"] = keyframe_url(f.get("video_id", ""), f.get("frame_index", 0))
        deduped.append(f)
    return deduped


def _filter_by_keywords(
    frames: list[Frame],
    ocr_keywords: Sequence[str] | None = None,
    asr_keywords: Sequence[str] | None = None,
    mode: str = "and",
    *,
    keywords: Sequence[str] | None = None,
    source: str = "all",
    ocr_mode: str | None = None,
    asr_mode: str | None = None,
) -> list[Frame]:
    """Drop frames whose OCR/ASR text does not match, in one ES round-trip."""
    has_any = bool(ocr_keywords) or bool(asr_keywords) or bool(keywords)
    if not has_any or not frames:
        return frames
    matched = es_client.match_frames_by_keywords(
        [_frame_key(f) for f in frames],
        keywords=keywords,
        mode=mode,
        source=source,
        ocr_keywords=ocr_keywords,
        asr_keywords=asr_keywords,
        ocr_mode=ocr_mode,
        asr_mode=asr_mode,
    )
    return [f for f in frames if _frame_key(f) in matched]


# ── Frame accessors ─────────────────────────────────────────────────────────
def _frame_index(frame: Frame) -> int:
    value = frame.get("frame_index", frame.get("frame_idx", 0))
    return int(value or 0)


def _timestamp(frame: Frame) -> float:
    value = float(frame.get("timestamp") or 0.0)
    return value if math.isfinite(value) else 0.0


def _similarity(frame: Frame) -> float:
    value = float(frame.get("vector_score") or 0.0)
    return value if math.isfinite(value) else 0.0


def _retrieval_rank(frame: Frame) -> int:
    value = frame.get("retrieval_rank")
    return int(value) if value is not None else 2**31 - 1


def _sorted_unique(frames: Iterable[Frame]) -> list[Frame]:
    """Deduplicate a layer, retaining its highest similarity per frame."""
    best: dict[FrameKey, Frame] = {}
    for frame in frames:
        key = _frame_key(frame)
        current = best.get(key)
        if current is None or _similarity(frame) > _similarity(current):
            best[key] = frame
    return sorted(best.values(), key=lambda frame: (_timestamp(frame), _frame_index(frame)))
