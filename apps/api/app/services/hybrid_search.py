"""Dense retrieval and post-filtering for single and temporal frame search.

Every temporal query box owns its raw Milvus Top-K and its enhancement, object,
OCR, and ASR settings. Parallel mode batches independent ANN requests into at
most three Top-K ranges. Sequential mode progressively restricts later ANN
requests to videos with a reachable predecessor. Both modes then retain nodes
on complete ordered paths and rank videos by their best dynamic-programming
path.
"""

import base64
import logging
import math
from collections import deque
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from app.services import video_meta
from app.services.encoders import manager
from app.services.es_client import es_client
from app.services.milvus_client import clamp_milvus_topk, get_milvus_client
from app.services.object_filter import filter_frame_keys, filter_frames, matching_frame_keys
from app.services.query_enhance import enhance_queries, enhance_query
from app.services.storage import keyframe_url, video_url

Frame = dict[str, Any]
Box = dict[str, Any]
FrameKey = tuple[Any, Any]
Vector = list[float] | None

TOPK_BUCKET_MAXIMA = (500, 1500, 5000)
FILTER_FETCH_CHUNK = 500

logger = logging.getLogger(__name__)


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


# ── Single-query search ─────────────────────────────────────────────────────
def search_text(
    query: str = "",
    tags: Sequence[str] | None = None,
    keywords: Sequence[str] | None = None,
    topk: int = 20,
    enhance: bool = True,
    tag_mode: str = "and",
    keyword_mode: str = "and",
    keyword_source: str = "all",
    ocr_keywords: Sequence[str] | None = None,
    asr_keywords: Sequence[str] | None = None,
    ocr_mode: str | None = None,
    asr_mode: str | None = None,
) -> list[Frame]:
    """Search by a vector query, filters, or both."""
    if enhance and query:
        query = enhance_query(query)
    if query:
        vec: list[float] = manager.embed_text([query])[0].tolist()
        frames = get_milvus_client(manager.active_collection_name()).search(
            vec, topk=clamp_milvus_topk(topk * 2)
        )
        frames = filter_frames(frames, tags, tag_mode)
        frames = _filter_by_keywords(
            frames,
            ocr_keywords=ocr_keywords,
            asr_keywords=asr_keywords,
            mode=keyword_mode,
            keywords=keywords,
            source=keyword_source,
            ocr_mode=ocr_mode,
            asr_mode=asr_mode,
        )
    else:
        frames = _filter_only_candidates({
            "tags": list(tags or []),
            "tag_match_mode": tag_mode,
            "keywords": list(keywords or []),
            "key_match_mode": keyword_mode,
            "keyword_source": keyword_source,
            "ocr_keywords": list(ocr_keywords or []),
            "asr_keywords": list(asr_keywords or []),
            "ocr_match_mode": ocr_mode,
            "asr_match_mode": asr_mode,
            "topk": topk,
        })
    frames = _enrich_frames(frames)
    for f in frames:
        f["score"] = f.get("vector_score", 0.0)
    frames.sort(key=lambda f: float(f["score"]), reverse=True)
    return frames[:topk]


def search_image(
    image_bytes: bytes,
    tags: Sequence[str] | None = None,
    keywords: Sequence[str] | None = None,
    topk: int = 20,
    tag_mode: str = "and",
    keyword_mode: str = "and",
    keyword_source: str = "all",
    ocr_keywords: Sequence[str] | None = None,
    asr_keywords: Sequence[str] | None = None,
    ocr_mode: str | None = None,
    asr_mode: str | None = None,
) -> list[Frame]:
    """Image search: embed -> Milvus -> Polars tags -> ES keywords."""
    vec: list[float] = manager.embed_image(image_bytes).tolist()
    frames = get_milvus_client(manager.active_collection_name()).search(
        vec, topk=clamp_milvus_topk(topk * 2)
    )
    frames = filter_frames(frames, tags, tag_mode)
    frames = _filter_by_keywords(
        frames,
        ocr_keywords=ocr_keywords,
        asr_keywords=asr_keywords,
        mode=keyword_mode,
        keywords=keywords,
        source=keyword_source,
        ocr_mode=ocr_mode,
        asr_mode=asr_mode,
    )
    frames = _enrich_frames(frames)
    for f in frames:
        f["score"] = f.get("vector_score", 0.0)
    frames.sort(key=lambda f: float(f["score"]), reverse=True)
    return frames[:topk]


def search_video_frames(
    video_id: str, frame_index: int | None = None, range: int = 5
) -> list[Frame]:
    """List a video's frames, optionally windowed around `frame_index`.

    Uses a scalar query — an ANN search with a zero vector scans the index for
    nothing.
    """
    try:
        milvus_frames = get_milvus_client(manager.active_collection_name()).query_frames(
            f"video_id == {_quote(video_id)}"
        )
    except Exception:
        return []
    frames = _enrich_frames(milvus_frames)
    try:
        texts = es_client.fetch_frame_texts(_frame_key(frame) for frame in frames)
    except Exception:
        logger.exception("Could not enrich navigator frames with Elasticsearch text")
        texts = {}
    for frame in frames:
        frame.update(texts.get(_frame_key(frame), {"ocr_text": "", "asr_text": ""}))
    frames.sort(key=lambda f: int(f.get("frame_index") or 0))
    if frame_index is None:
        return frames
    pos = next((i for i, f in enumerate(frames) if f.get("frame_index") == frame_index), None)
    if pos is None:
        return frames
    return frames[max(0, pos - range):pos + range + 1]


def search_similar_frames(video_id: str, frame_index: int, topk: int = 12) -> list[Frame]:
    milvus = get_milvus_client(manager.active_collection_name())
    embedding = milvus.get_frame_embedding(video_id, frame_index)
    if embedding is None:
        return []
    milvus_frames = milvus.search(embedding, topk=topk + 1)
    milvus_frames = [
        f for f in milvus_frames
        if not (f.get("video_id") == video_id and f.get("frame_index") == frame_index)
    ][:topk]
    for f in milvus_frames:
        f["score"] = f.get("vector_score", 0.0)
    frames = _enrich_frames(milvus_frames)
    frames.sort(key=lambda f: float(f.get("score", 0.0)), reverse=True)
    return frames


# ── Multi-box fan-out ───────────────────────────────────────────────────────
def _resolve_enhance(box: Box, default: bool) -> bool:
    override = box.get("enhance")
    return default if override is None else bool(override)


def _box_vectors(boxes: Sequence[Box], enhance_default: bool) -> list[Vector]:
    """One CLIP forward pass for all text boxes and one for all image boxes.

    Returns a list aligned to `boxes`; entries are None for boxes that carry
    neither text nor an image.
    """
    vectors: list[Vector] = [None] * len(boxes)

    text_idx = [i for i, b in enumerate(boxes) if b.get("text")]
    image_idx = [i for i, b in enumerate(boxes) if not b.get("text") and b.get("image")]

    if text_idx:
        texts = {i: str(boxes[i]["text"]) for i in text_idx}
        to_enhance = [i for i in text_idx if _resolve_enhance(boxes[i], enhance_default)]
        if to_enhance:
            enhanced = enhance_queries([texts[i] for i in to_enhance])
            texts.update(dict(zip(to_enhance, enhanced)))
        encoded = manager.embed_text([texts[i] for i in text_idx])
        for i, vec in zip(text_idx, encoded):
            vectors[i] = vec.tolist()

    if image_idx:
        blobs: list[bytes] = []
        decoded_idx: list[int] = []
        for i in image_idx:
            try:
                blobs.append(base64.b64decode(boxes[i]["image"]))
                decoded_idx.append(i)
            except Exception:
                continue
        if blobs:
            encoded = manager.embed_images(blobs)
            for i, vec in zip(decoded_idx, encoded):
                vectors[i] = vec.tolist()

    return vectors


def _apply_box_object_filters(
    boxes: Sequence[Box], per_box: list[list[Frame]]
) -> list[list[Frame]]:
    """Post-filter every box's ranked Milvus candidates by RF-DETR classes."""
    for i, box in enumerate(boxes):
        per_box[i] = filter_frames(
            per_box[i], box.get("tags"), box.get("tag_match_mode", "and")
        )
    return per_box


def _apply_box_keywords(
    boxes: Sequence[Box], per_box: list[list[Frame]]
) -> list[list[Frame]]:
    for i, box in enumerate(boxes):
        per_box[i] = _filter_by_keywords(
            per_box[i],
            ocr_keywords=box.get("ocr_keywords"),
            asr_keywords=box.get("asr_keywords"),
            mode=box.get("key_match_mode", "and"),
            keywords=box.get("keywords"),
            source=box.get("keyword_source", "all"),
            ocr_mode=box.get("ocr_match_mode"),
            asr_mode=box.get("asr_match_mode"),
        )
    return per_box


def _box_topk(box: Box) -> int:
    """Return the validated per-box raw Milvus candidate count."""
    return max(1, min(int(box.get("topk") or 500), TOPK_BUCKET_MAXIMA[-1]))


def _topk_bucket(topk: int) -> int:
    return next(maximum for maximum in TOPK_BUCKET_MAXIMA if topk <= maximum)


def _post_filter_boxes(
    boxes: Sequence[Box], per_box: list[list[Frame]]
) -> list[list[Frame]]:
    per_box = _apply_box_object_filters(boxes, per_box)
    return _apply_box_keywords(boxes, per_box)


def _has_keywords(box: Box) -> bool:
    return bool(box.get("ocr_keywords") or box.get("asr_keywords") or box.get("keywords"))


def _filter_only_candidates(
    box: Box, allowed_video_ids: set[str] | None = None
) -> list[Frame]:
    """Build a filter-ranked layer, then resolve metadata from active Milvus."""
    limit = _box_topk(box)
    tags = box.get("tags") or []
    has_keywords = _has_keywords(box)
    if not tags and not has_keywords:
        return []

    if has_keywords:
        raw_keys: Iterable[FrameKey] = (
            (video_id, frame_index)
            for video_id, frame_index, _score in es_client.iter_keyword_frame_hits(
                keywords=box.get("keywords"),
                mode=box.get("key_match_mode", "and"),
                source=box.get("keyword_source", "all"),
                ocr_keywords=box.get("ocr_keywords"),
                asr_keywords=box.get("asr_keywords"),
                ocr_mode=box.get("ocr_match_mode"),
                asr_mode=box.get("asr_match_mode"),
                allowed_video_ids=sorted(allowed_video_ids) if allowed_video_ids is not None else None,
                page_size=FILTER_FETCH_CHUNK,
            )
        )
    else:
        raw_keys = matching_frame_keys(
            tags,
            box.get("tag_match_mode", "and"),
            allowed_video_ids=allowed_video_ids,
        )

    milvus = get_milvus_client(manager.active_collection_name())
    results: list[Frame] = []
    seen: set[FrameKey] = set()
    pending: list[FrameKey] = []

    def flush() -> None:
        nonlocal pending
        if not pending or len(results) >= limit:
            pending = []
            return
        keys = pending
        pending = []
        if tags and has_keywords:
            keys = filter_frame_keys(keys, tags, box.get("tag_match_mode", "and"))
        for frame in milvus.query_frame_keys(keys):
            frame["vector_score"] = 0.0
            frame["score"] = 0.0
            frame["filter_only"] = True
            frame["retrieval_rank"] = len(results)
            results.append(frame)
            if len(results) >= limit:
                break

    for raw_key in raw_keys:
        key = (str(raw_key[0]), int(raw_key[1]))
        if key in seen:
            continue
        seen.add(key)
        pending.append(key)
        needed = max(1, limit - len(results))
        if len(pending) >= min(FILTER_FETCH_CHUNK, needed):
            flush()
            if len(results) >= limit:
                break
    flush()
    return results


def _parallel_retrieve(
    boxes: Sequence[Box], vectors: Sequence[Vector]
) -> list[list[Frame]]:
    """Retrieve independent boxes in at most three concurrent Milvus batches.

    Boxes are grouped by the 1..500, 501..1500, and 1501..5000 ranges. A
    bucket uses its largest requested Top-K for its one Milvus call, then each
    result list is truncated to the owning box's Top-K *before* post-filters.
    """
    per_box: list[list[Frame]] = [[] for _ in boxes]
    buckets: dict[int, list[int]] = {}
    for index, vector in enumerate(vectors):
        if vector is not None:
            buckets.setdefault(_topk_bucket(_box_topk(boxes[index])), []).append(index)
    milvus = get_milvus_client(manager.active_collection_name()) if buckets else None

    def search_bucket(indices: list[int]) -> tuple[list[int], list[list[Frame]]]:
        limit = max(_box_topk(boxes[index]) for index in indices)
        embeddings: list[list[float]] = []
        for index in indices:
            vector = vectors[index]
            assert vector is not None
            embeddings.append(vector)
        assert milvus is not None
        return indices, milvus.search_batch(embeddings, topk=limit)

    if buckets:
        with ThreadPoolExecutor(max_workers=len(buckets)) as executor:
            futures = [executor.submit(search_bucket, indices) for indices in buckets.values()]
            for future in as_completed(futures):
                indices, batched = future.result()
                for index, frames in zip(indices, batched):
                    per_box[index] = frames[:_box_topk(boxes[index])]

    vector_indices = [index for index, vector in enumerate(vectors) if vector is not None]
    if vector_indices:
        filtered = _post_filter_boxes(
            [boxes[index] for index in vector_indices],
            [per_box[index] for index in vector_indices],
        )
        for index, frames in zip(vector_indices, filtered):
            per_box[index] = frames
    for index, vector in enumerate(vectors):
        if vector is None:
            per_box[index] = _filter_only_candidates(boxes[index])
    return per_box


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


def _edge(predecessor: Frame, successor: Frame, window: float) -> bool:
    gap = _timestamp(successor) - _timestamp(predecessor)
    return (
        _frame_index(predecessor) < _frame_index(successor)
        and 0.0 < gap <= window
    )


def _sorted_unique(frames: Iterable[Frame]) -> list[Frame]:
    """Deduplicate a layer, retaining its highest similarity per frame."""
    best: dict[FrameKey, Frame] = {}
    for frame in frames:
        key = _frame_key(frame)
        current = best.get(key)
        if current is None or _similarity(frame) > _similarity(current):
            best[key] = frame
    return sorted(best.values(), key=lambda frame: (_timestamp(frame), _frame_index(frame)))


def _combined_coordinates_are_monotonic(left: Sequence[Frame], right: Sequence[Frame]) -> bool:
    combined = sorted((*left, *right), key=lambda frame: (_timestamp(frame), _frame_index(frame)))
    return all(
        _frame_index(previous) <= _frame_index(current)
        for previous, current in zip(combined, combined[1:])
    )


def _forward_flags(
    previous: Sequence[Frame],
    current: Sequence[Frame],
    previous_flags: Sequence[bool],
    window: float,
) -> list[bool]:
    """Mark current nodes with a reachable predecessor in the prior layer."""
    if not _combined_coordinates_are_monotonic(previous, current):
        return [
            any(flag and _edge(candidate, frame, window) for candidate, flag in zip(previous, previous_flags))
            for frame in current
        ]

    active: deque[int] = deque()
    high = 0
    flags: list[bool] = []
    for frame in current:
        timestamp = _timestamp(frame)
        while high < len(previous) and _timestamp(previous[high]) < timestamp:
            if previous_flags[high]:
                active.append(high)
            high += 1
        while active and _timestamp(previous[active[0]]) < timestamp - window:
            active.popleft()
        flags.append(bool(active and _edge(previous[active[0]], frame, window)))
    return flags


def _backward_flags(
    current: Sequence[Frame],
    following: Sequence[Frame],
    following_flags: Sequence[bool],
    window: float,
) -> list[bool]:
    """Mark current nodes with a reachable successor in the next layer."""
    if not _combined_coordinates_are_monotonic(current, following):
        return [
            any(flag and _edge(frame, candidate, window) for candidate, flag in zip(following, following_flags))
            for frame in current
        ]

    active: deque[int] = deque()
    low = 0
    high = 0
    flags: list[bool] = []
    for frame in current:
        timestamp = _timestamp(frame)
        while high < len(following) and _timestamp(following[high]) <= timestamp + window:
            if following_flags[high]:
                active.append(high)
            high += 1
        while low < high and _timestamp(following[low]) <= timestamp:
            if active and active[0] == low:
                active.popleft()
            low += 1
        # Coordinates are monotonic here; the newest active successor has the
        # largest frame index, so it decides whether any strict-forward edge exists.
        flags.append(bool(active and _edge(frame, following[active[-1]], window)))
    return flags


def _retain_forward_reachable(
    previous: Sequence[Frame], current: Sequence[Frame], window: float
) -> list[Frame]:
    previous_by_video: dict[str, list[Frame]] = {}
    for frame in previous:
        previous_by_video.setdefault(str(frame.get("video_id") or ""), []).append(frame)

    keep: set[FrameKey] = set()
    current_by_video: dict[str, list[Frame]] = {}
    for frame in current:
        current_by_video.setdefault(str(frame.get("video_id") or ""), []).append(frame)
    for video_id, frames in current_by_video.items():
        prior = _sorted_unique(previous_by_video.get(video_id, []))
        layer = _sorted_unique(frames)
        if not prior:
            continue
        flags = _forward_flags(prior, layer, [True] * len(prior), window)
        keep.update(_frame_key(frame) for frame, flag in zip(layer, flags) if flag)
    return [frame for frame in current if _frame_key(frame) in keep]


def _sequential_retrieve(
    boxes: Sequence[Box], vectors: Sequence[Vector], window: float
) -> list[list[Frame]]:
    """Search each stage inside the videos surviving its predecessor stage."""
    per_box: list[list[Frame]] = [[] for _ in boxes]
    if not boxes:
        return per_box

    milvus = get_milvus_client(manager.active_collection_name())
    previous: list[Frame] = []
    for index, (box, vector) in enumerate(zip(boxes, vectors)):
        expression = None
        allowed_video_ids: set[str] | None = None
        if index:
            video_ids = sorted({str(frame.get("video_id")) for frame in previous if frame.get("video_id")})
            expression = _video_expr(video_ids)
            if expression is None:
                return per_box
            allowed_video_ids = set(video_ids)
        if vector is None:
            filtered = _filter_only_candidates(box, allowed_video_ids=allowed_video_ids)
        else:
            frames = milvus.search(vector, topk=_box_topk(box), expr=expression)
            filtered = _post_filter_boxes([box], [frames[:_box_topk(box)]])[0]
        if index:
            filtered = _retain_forward_reachable(previous, filtered, window)
        per_box[index] = filtered
        previous = filtered
        if not previous:
            return per_box
    return per_box


@dataclass(frozen=True)
class _PathState:
    score_sum: float
    start_time: float
    start_frame: int
    frame_indexes: tuple[int, ...]


def _predecessor_key(state: _PathState) -> tuple[float, float, int, tuple[int, ...]]:
    # For a fixed successor: high sum, later start (short span), earlier first
    # frame, then lexicographically earlier path.
    return (-state.score_sum, -state.start_time, state.start_frame, state.frame_indexes)


def _best_path(by_box: Sequence[list[Frame]], window: float) -> tuple[list[Frame], float] | None:
    """Find the highest-scoring complete path using dense layer positions."""
    if not by_box or any(not layer for layer in by_box):
        return None

    previous_states: list[_PathState | None] = [
        _PathState(_similarity(frame), _timestamp(frame), _frame_index(frame), (_frame_index(frame),))
        for frame in by_box[0]
    ]
    parents: list[list[int]] = [[-1] * len(by_box[0])]

    for layer_index in range(1, len(by_box)):
        previous = by_box[layer_index - 1]
        current = by_box[layer_index]
        current_states: list[_PathState | None] = [None] * len(current)
        current_parents = [-1] * len(current)
        optimized = _combined_coordinates_are_monotonic(previous, current)

        if optimized:
            candidates: deque[int] = deque()
            high = 0
            for current_index, frame in enumerate(current):
                timestamp = _timestamp(frame)
                while high < len(previous) and _timestamp(previous[high]) < timestamp:
                    state = previous_states[high]
                    if state is not None:
                        while (
                            candidates
                            and _predecessor_key(state)
                            < _predecessor_key(previous_states[candidates[-1]])  # type: ignore[arg-type]
                        ):
                            candidates.pop()
                        candidates.append(high)
                    high += 1
                while candidates and _timestamp(previous[candidates[0]]) < timestamp - window:
                    candidates.popleft()
                predecessor = candidates[0] if candidates else -1
                if predecessor >= 0 and not _edge(previous[predecessor], frame, window):
                    predecessor = -1
                if predecessor >= 0:
                    prior = previous_states[predecessor]
                    assert prior is not None
                    current_states[current_index] = _PathState(
                        prior.score_sum + _similarity(frame),
                        prior.start_time,
                        prior.start_frame,
                        prior.frame_indexes + (_frame_index(frame),),
                    )
                    current_parents[current_index] = predecessor
        else:
            for current_index, frame in enumerate(current):
                eligible = [
                    index
                    for index, state in enumerate(previous_states)
                    if state is not None and _edge(previous[index], frame, window)
                ]
                if not eligible:
                    continue
                predecessor = min(
                    eligible,
                    key=lambda index: _predecessor_key(previous_states[index]),  # type: ignore[arg-type]
                )
                prior = previous_states[predecessor]
                assert prior is not None
                current_states[current_index] = _PathState(
                    prior.score_sum + _similarity(frame),
                    prior.start_time,
                    prior.start_frame,
                    prior.frame_indexes + (_frame_index(frame),),
                )
                current_parents[current_index] = predecessor

        if not any(state is not None for state in current_states):
            return None
        parents.append(current_parents)
        previous_states = current_states

    final_candidates = [index for index, state in enumerate(previous_states) if state is not None]
    if not final_candidates:
        return None

    def final_key(index: int) -> tuple[float, float, int, tuple[int, ...]]:
        state = previous_states[index]
        assert state is not None
        span = _timestamp(by_box[-1][index]) - state.start_time
        return (-state.score_sum, span, state.start_frame, state.frame_indexes)

    position = min(final_candidates, key=final_key)
    final_state = previous_states[position]
    assert final_state is not None
    positions = [position]
    for layer_index in range(len(by_box) - 1, 0, -1):
        position = parents[layer_index][position]
        positions.append(position)
    positions.reverse()
    return [by_box[index][position] for index, position in enumerate(positions)], final_state.score_sum


def _single_box_response(per_box: Sequence[list[Frame]], mode: str) -> dict[str, Any]:
    by_video: dict[str, list[Frame]] = {}
    for frame in per_box[0] if per_box else []:
        video_id = str(frame.get("video_id") or "")
        if video_id:
            by_video.setdefault(video_id, []).append(frame)

    videos: list[dict[str, Any]] = []
    for video_id, candidates in by_video.items():
        layer = _sorted_unique(candidates)
        filter_only = all(bool(frame.get("filter_only")) for frame in layer)
        valid_frames: list[Frame] = []
        for frame in layer:
            result = dict(frame)
            similarity = _similarity(frame)
            result["score"] = similarity
            result["matches"] = [{"query_index": 0, "similarity": similarity}]
            valid_frames.append(result)
        valid_frames = _enrich_frames(valid_frames)
        if filter_only:
            best = min(layer, key=lambda frame: (_retrieval_rank(frame), _frame_index(frame)))
        else:
            best = min(layer, key=lambda frame: (-_similarity(frame), _frame_index(frame)))
        sequence_frame = _enrich_frames([dict(best)])[0]
        sequence_frame["score"] = _similarity(best)
        sequence_frame["query_index"] = 0
        sequence_frame["similarity"] = _similarity(best)
        videos.append({
            "video_id": video_id,
            "video_score": _similarity(best),
            "has_vector_score": not filter_only,
            "valid_frames": valid_frames,
            "best_sequence": {
                "sequence_id": f"{video_id}:{_frame_index(best)}",
                "sequence_score": _similarity(best),
                "total_span_seconds": 0.0,
                "frames": [sequence_frame],
            },
        })
    videos.sort(
        key=lambda video: (
            0 if bool(video["has_vector_score"]) else 1,
            -float(video["video_score"]),
            _retrieval_rank(video["best_sequence"]["frames"][0]),
            _frame_index(video["best_sequence"]["frames"][0]),
            video["video_id"],
        )
    )
    return {
        "mode": mode,
        "videos": videos,
        "total_videos": len(videos),
        "total_valid_frames": sum(len(video["valid_frames"]) for video in videos),
    }


def build_temporal_response(
    per_box: Sequence[list[Frame]], window: float, mode: str
) -> dict[str, Any]:
    """Build all complete-path nodes and one DP-ranked sequence per video."""
    if len(per_box) <= 1:
        return _single_box_response(per_box, mode)
    empty = {"mode": mode, "videos": [], "total_videos": 0, "total_valid_frames": 0}
    if any(not layer for layer in per_box):
        return empty

    video_sets = [
        {str(frame.get("video_id")) for frame in layer if frame.get("video_id")}
        for layer in per_box
    ]
    common_videos = set.intersection(*video_sets)
    videos: list[dict[str, Any]] = []
    for video_id in common_videos:
        by_box = [
            _sorted_unique(frame for frame in layer if str(frame.get("video_id")) == video_id)
            for layer in per_box
        ]
        forward: list[list[bool]] = [[True] * len(by_box[0])]
        for index in range(1, len(by_box)):
            forward.append(_forward_flags(by_box[index - 1], by_box[index], forward[-1], window))
        if not any(forward[-1]):
            continue

        backward: list[list[bool]] = [[] for _ in by_box]
        backward[-1] = [True] * len(by_box[-1])
        for index in range(len(by_box) - 2, -1, -1):
            backward[index] = _backward_flags(
                by_box[index], by_box[index + 1], backward[index + 1], window
            )
        valid = [
            [left and right for left, right in zip(forward[index], backward[index])]
            for index in range(len(by_box))
        ]

        best_path = _best_path(by_box, window)
        if best_path is None:
            continue
        path, score_sum = best_path
        sequence_score = score_sum / len(by_box)

        deduped: dict[FrameKey, Frame] = {}
        for query_index, layer in enumerate(by_box):
            for frame, is_valid in zip(layer, valid[query_index]):
                if not is_valid:
                    continue
                key = _frame_key(frame)
                similarity = _similarity(frame)
                result = deduped.get(key)
                if result is None:
                    result = dict(frame)
                    result["score"] = similarity
                    result["matches"] = []
                    deduped[key] = result
                else:
                    result["score"] = max(float(result["score"]), similarity)
                result["matches"].append({"query_index": query_index, "similarity": similarity})
        valid_frames = sorted(
            _enrich_frames(deduped.values()),
            key=lambda frame: (_frame_index(frame), _timestamp(frame)),
        )
        for frame in valid_frames:
            frame["matches"].sort(key=lambda match: int(match["query_index"]))

        sequence_frames: list[Frame] = []
        for query_index, frame in enumerate(path):
            result = dict(frame)
            result["score"] = _similarity(frame)
            result["query_index"] = query_index
            result["similarity"] = _similarity(frame)
            sequence_frames.append(result)
        sequence_frames = _enrich_frames(sequence_frames)
        first = sequence_frames[0]
        last = sequence_frames[-1]
        sequence_id = f"{video_id}:" + "-".join(str(_frame_index(frame)) for frame in path)
        videos.append({
            "video_id": video_id,
            "video_score": sequence_score,
            "has_vector_score": any(not bool(frame.get("filter_only")) for frame in path),
            "valid_frames": valid_frames,
            "best_sequence": {
                "sequence_id": sequence_id,
                "sequence_score": sequence_score,
                "total_span_seconds": _timestamp(last) - _timestamp(first),
                "frames": sequence_frames,
            },
        })

    videos.sort(
        key=lambda video: (
            -float(video["video_score"]),
            float(video["best_sequence"]["total_span_seconds"]),
            _frame_index(video["best_sequence"]["frames"][0]),
            tuple(_frame_index(frame) for frame in video["best_sequence"]["frames"]),
            video["video_id"],
        )
    )
    return {
        "mode": mode,
        "videos": videos,
        "total_videos": len(videos),
        "total_valid_frames": sum(len(video["valid_frames"]) for video in videos),
    }


def multi_box_search(
    box_queries: Sequence[Box],
    temporal_window: float = 90.0,
    enhance: bool = True,
    mode: str = "parallel",
) -> dict[str, Any]:
    """Run temporal search with per-box retrieval and structured video results."""
    if not box_queries:
        return {"mode": mode, "videos": [], "total_videos": 0, "total_valid_frames": 0}

    vectors = _box_vectors(box_queries, enhance)
    if len(box_queries) == 1 or mode == "parallel":
        per_box = _parallel_retrieve(box_queries, vectors)
    else:
        per_box = _sequential_retrieve(box_queries, vectors, temporal_window)
    return build_temporal_response(per_box, temporal_window, mode)
