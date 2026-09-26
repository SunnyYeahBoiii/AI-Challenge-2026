"""Single-query search and multi-box fan-out retrieval (parallel/sequential)."""

import base64
import logging
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.encoders import manager
from app.services.es_client import es_client
from app.services.hybrid_search.common import (
    FILTER_FETCH_CHUNK,
    TOPK_BUCKET_MAXIMA,
    Box,
    Frame,
    FrameKey,
    Vector,
    _collapse_shots,
    _and_expr,
    _enrich_frames,
    _filter_by_keywords,
    _frame_key,
    _fuse_scores,
    _quote,
    _sorted_unique,
    _video_expr,
    _video_prefix_expr,
)
from app.services.hybrid_search.temporal_paths import _forward_flags
from app.services.milvus_client import clamp_milvus_topk, get_milvus_client
from app.services.object_filter import filter_frame_keys, filter_frames, matching_frame_keys
from app.services.query_enhance import enhance_queries, enhance_query

logger = logging.getLogger(__name__)


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
    ocr_search_mode: str = "unordered",
    asr_search_mode: str = "exact",
    keyword_field_mode: str = "and",
    video_prefixes: Sequence[str] | None = None,
) -> list[Frame]:
    """Search by a vector query, filters, or both."""
    if enhance and query:
        query = enhance_query(query)
    if query:
        vec: list[float] = manager.embed_text([query])[0].tolist()
        frames = get_milvus_client(manager.active_collection_name()).search(
            vec,
            topk=clamp_milvus_topk(topk * 2),
            expr=_video_prefix_expr(video_prefixes),
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
            ocr_search_mode=ocr_search_mode,
            asr_search_mode=asr_search_mode,
            keyword_field_mode=keyword_field_mode,
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
            "ocr_search_mode": ocr_search_mode,
            "asr_search_mode": asr_search_mode,
            "keyword_field_mode": keyword_field_mode,
            "topk": topk,
            "video_prefixes": list(video_prefixes or []),
        })
    frames = _enrich_frames(frames)
    frames = _collapse_shots(_fuse_scores(frames))
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
    ocr_search_mode: str = "unordered",
    asr_search_mode: str = "exact",
    keyword_field_mode: str = "and",
    video_prefixes: Sequence[str] | None = None,
) -> list[Frame]:
    """Image search: embed -> Milvus -> Polars tags -> ES keywords."""
    vec: list[float] = manager.embed_image(image_bytes).tolist()
    frames = get_milvus_client(manager.active_collection_name()).search(
        vec,
        topk=clamp_milvus_topk(topk * 2),
        expr=_video_prefix_expr(video_prefixes),
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
        ocr_search_mode=ocr_search_mode,
        asr_search_mode=asr_search_mode,
        keyword_field_mode=keyword_field_mode,
    )
    frames = _enrich_frames(frames)
    frames = _collapse_shots(_fuse_scores(frames))
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
        logger.exception("Could not list frames for video %s", video_id)
        raise
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
            ocr_search_mode=box.get("ocr_search_mode", "unordered"),
            asr_search_mode=box.get("asr_search_mode", "exact"),
            keyword_field_mode=box.get("keyword_field_mode", "and"),
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
    box: Box,
    allowed_video_ids: set[str] | None = None,
    video_prefixes: Sequence[str] | None = None,
) -> list[Frame]:
    """Build a filter-ranked layer, then resolve metadata from active Milvus."""
    limit = _box_topk(box)
    tags = box.get("tags") or []
    has_keywords = _has_keywords(box)
    if not tags and not has_keywords:
        return []

    text_scores: dict[FrameKey, float] = {}
    if has_keywords:
        def keyword_keys() -> Iterable[FrameKey]:
            for video_id, frame_index, score in es_client.iter_keyword_frame_hits(
                keywords=box.get("keywords"),
                mode=box.get("key_match_mode", "and"),
                source=box.get("keyword_source", "all"),
                ocr_keywords=box.get("ocr_keywords"),
                asr_keywords=box.get("asr_keywords"),
                ocr_mode=box.get("ocr_match_mode"),
                asr_mode=box.get("asr_match_mode"),
                ocr_search_mode=box.get("ocr_search_mode", "unordered"),
                asr_search_mode=box.get("asr_search_mode", "exact"),
                keyword_field_mode=box.get("keyword_field_mode", "and"),
                allowed_video_ids=sorted(allowed_video_ids) if allowed_video_ids is not None else None,
                video_prefixes=video_prefixes,
                page_size=FILTER_FETCH_CHUNK,
            ):
                key = (video_id, frame_index)
                text_scores[key] = score
                yield key

        raw_keys: Iterable[FrameKey] = keyword_keys()
    else:
        raw_keys = matching_frame_keys(
            tags,
            box.get("tag_match_mode", "and"),
            allowed_video_ids=allowed_video_ids,
            video_prefixes=video_prefixes,
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
            text_score = text_scores.get(_frame_key(frame), 0.0)
            frame["text_score"] = text_score
            frame["score"] = text_score
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
    boxes: Sequence[Box], vectors: Sequence[Vector], video_prefixes: Sequence[str] | None = None
) -> list[list[Frame]]:
    """Retrieve independent boxes in at most three concurrent Milvus batches.

    Boxes are grouped by the 1..500, 501..1500, 1501..5000 and 5001..10000
    ranges. A bucket uses its largest requested Top-K for its one Milvus call, then each
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
        return indices, milvus.search_batch(
            embeddings, topk=limit, expr=_video_prefix_expr(video_prefixes)
        )

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
            per_box[index] = _filter_only_candidates(
                boxes[index], video_prefixes=video_prefixes
            )
    return per_box


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
    boxes: Sequence[Box], vectors: Sequence[Vector], window: float,
    video_prefixes: Sequence[str] | None = None,
) -> list[list[Frame]]:
    """Search each stage inside the videos surviving its predecessor stage."""
    per_box: list[list[Frame]] = [[] for _ in boxes]
    if not boxes:
        return per_box

    milvus = get_milvus_client(manager.active_collection_name())
    previous: list[Frame] = []
    for index, (box, vector) in enumerate(zip(boxes, vectors)):
        expression = _video_prefix_expr(video_prefixes)
        allowed_video_ids: set[str] | None = None
        if index:
            video_ids = sorted({str(frame.get("video_id")) for frame in previous if frame.get("video_id")})
            video_expr = _video_expr(video_ids)
            if video_expr is None:
                return per_box
            expression = _and_expr(expression, video_expr) if expression else video_expr
            allowed_video_ids = set(video_ids)
        if vector is None:
            if video_prefixes:
                filtered = _filter_only_candidates(
                    box,
                    allowed_video_ids=allowed_video_ids,
                    video_prefixes=video_prefixes,
                )
            else:
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


# Re-exported for the response builder; keeps single import site per concept.
__all__ = [
    "search_text",
    "search_image",
    "search_video_frames",
    "search_similar_frames",
    "_apply_box_keywords",
    "_box_vectors",
    "_filter_only_candidates",
    "_parallel_retrieve",
    "_retain_forward_reachable",
    "_sequential_retrieve",
]
