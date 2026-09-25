"""Shared frame helpers: aliases, enrichment, keyword filtering, and fusion."""

import math
from collections.abc import Iterable, Sequence
from typing import Any

from app.config import Config
from app.services import video_meta
from app.services.es_client import es_client
from app.services.storage import keyframe_url, video_url

Frame = dict[str, Any]
Box = dict[str, Any]
FrameKey = tuple[Any, Any]
Vector = list[float] | None

TOPK_BUCKET_MAXIMA = (500, 1500, 5000, 10000)
FILTER_FETCH_CHUNK = 500


# ── Filter expressions ──────────────────────────────────────────────────────
def _quote(value: Any) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _video_expr(video_ids: Sequence[str]) -> str | None:
    if not video_ids:
        return None
    return f"video_id in [{', '.join(_quote(v) for v in video_ids)}]"


def _video_prefix_expr(prefixes: Sequence[str] | None) -> str | None:
    """Build a Milvus expression that limits results to video ID prefixes."""
    unique_prefixes = sorted(set(prefixes or []))
    if not unique_prefixes:
        return None
    return " or ".join(f"video_id like {_quote(f'{prefix}%')}" for prefix in unique_prefixes)


def _and_expr(*expressions: str | None) -> str | None:
    """Combine optional Milvus predicates without changing their precedence."""
    parts = [f"({expression})" for expression in expressions if expression]
    return " and ".join(parts) if parts else None


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
    ocr_search_mode: str = "exact",
    asr_search_mode: str = "exact",
    keyword_field_mode: str = "and",
) -> list[Frame]:
    """Drop frames whose OCR/ASR text does not match, in one ES round-trip.

    Survivors carry their BM25 relevance as `text_score`, so ranking can tell a
    frame the keyword genuinely identifies from one where it only appears in a
    station watermark.
    """
    has_any = bool(ocr_keywords) or bool(asr_keywords) or bool(keywords)
    if not has_any or not frames:
        return frames
    scored = es_client.score_frames_by_keywords(
        [_frame_key(f) for f in frames],
        keywords=keywords,
        mode=mode,
        source=source,
        ocr_keywords=ocr_keywords,
        asr_keywords=asr_keywords,
        ocr_mode=ocr_mode,
        asr_mode=asr_mode,
        ocr_search_mode=ocr_search_mode,
        asr_search_mode=asr_search_mode,
        keyword_field_mode=keyword_field_mode,
    )
    survivors: list[Frame] = []
    for frame in frames:
        key = _frame_key(frame)
        if key not in scored:
            continue
        frame["text_score"] = scored[key]
        survivors.append(frame)
    return survivors


# ── Fusion and shot collapsing ──────────────────────────────────────────────
def _ranks(frames: Sequence[Frame], field: str) -> dict[int, int] | None:
    """Rank frames by `field` descending, or None when no frame carries it.

    Returning None matters: a source nobody scored must drop out of the fusion
    entirely rather than contribute an identical term to every frame.
    """
    present = [
        index
        for index, frame in enumerate(frames)
        if frame.get(field) is not None
        # filter_only frames carry a placeholder vector_score of 0.0 for display;
        # they were never vector-ranked and must not enter the vector fusion term.
        and not (field == "vector_score" and frame.get("filter_only"))
    ]
    if not present:
        return None
    present.sort(key=lambda index: float(frames[index].get(field) or 0.0), reverse=True)
    return {index: rank for rank, index in enumerate(present, start=1)}


def _fuse_scores(frames: list[Frame]) -> list[Frame]:
    """Score frames by Reciprocal Rank Fusion of their vector and text ranks.

    RRF works on ranks, so cosine similarity and BM25 need no shared scale —
    normalising two unbounded, differently-shaped distributions against each
    other is what usually goes wrong here. With a single source present it
    degenerates to that source's own ordering.

    Note this fuses *within* the candidate set the vector search returned; it
    re-ranks, it does not recall frames Milvus never surfaced.
    """
    vector_ranks = _ranks(frames, "vector_score")
    text_ranks = _ranks(frames, "text_score")
    k = Config.RRF_K
    for index, frame in enumerate(frames):
        score = 0.0
        if vector_ranks is not None and index in vector_ranks:
            score += Config.RRF_VECTOR_WEIGHT / (k + vector_ranks[index])
        if text_ranks is not None and index in text_ranks:
            score += Config.RRF_TEXT_WEIGHT / (k + text_ranks[index])
        frame["score"] = score
    frames.sort(key=lambda frame: float(frame.get("score") or 0.0), reverse=True)
    return frames


def _collapse_shots(frames: list[Frame]) -> list[Frame]:
    """Keep the best frame per shot, parking the rest under `shot_siblings`.

    ASR is transcribed on a rolling window, so consecutive keyframes of one shot
    carry near-identical text — 89k adjacent pairs are byte-identical. Without
    this, one transcript hit floods the page with the same moment over and over.

    Frames are expected pre-sorted by score; siblings are kept as thumbnail-sized
    references, not discarded, so the UI can expand a shot without a refetch and
    without carrying a second full frame payload per sibling. Callers on the
    TRAKE path must not use this — temporal paths need every frame of a shot to
    build event sequences.
    """
    if not Config.ES_DEDUPE_BY_SHOT:
        return frames
    best: dict[tuple[str, int], Frame] = {}
    collapsed: list[Frame] = []
    for frame in frames:
        shot_idx = frame.get("shot_idx")
        if shot_idx is None:
            collapsed.append(frame)
            continue
        key = (str(frame.get("video_id") or ""), int(shot_idx))
        leader = best.get(key)
        if leader is None:
            best[key] = frame
            frame.setdefault("shot_siblings", [])
            collapsed.append(frame)
            continue
        leader["shot_siblings"].append(_sibling_ref(frame))
    return collapsed


def _sibling_ref(frame: Frame) -> Frame:
    return {
        "video_id": frame.get("video_id"),
        "frame_index": frame.get("frame_index"),
        "timestamp": frame.get("timestamp"),
        "thumbnail_url": frame.get("thumbnail_url"),
        "score": frame.get("score"),
    }


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
