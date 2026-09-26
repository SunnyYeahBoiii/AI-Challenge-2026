"""Visual repeat detection using a precomputed graph with a Milvus fallback."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
import threading
import numpy as np

from app.services.encoders import manager
from app.services.milvus_client import get_milvus_client
from app.services.repeat_graph import (
    RepeatFrameDetails,
    RepeatFrameReference,
    get_repeat_graph,
)


FrameKey = tuple[str, int]
RepeatCandidate = tuple[str, int, float]


REPEAT_SIMILARITY_THRESHOLD = 0.92
L25_REPEAT_SIMILARITY_THRESHOLD = 0.97
SAME_VIDEO_MIN_TIMESTAMP_GAP_SECONDS = 6.0
L25_SAME_VIDEO_MIN_TIMESTAMP_GAP_SECONDS = 15.0
SIMILARITY_COMPARISON_EPSILON = 1e-6
MAX_REPEAT_FRAMES = 1500
_MATRIX_BLOCK_SIZE = 256
_CACHE_LIMIT = 32
_repeat_cache: OrderedDict[
    tuple[str, tuple[RepeatCandidate, ...]], dict[FrameKey, RepeatFrameDetails]
] = OrderedDict()
_cache_lock = threading.Lock()


def clear_repeat_cache() -> None:
    """Clear in-memory repeat results; used by tests and process lifecycle hooks."""
    with _cache_lock:
        _repeat_cache.clear()


def _canonical_candidates(frames: Sequence[RepeatCandidate]) -> tuple[RepeatCandidate, ...]:
    """Deduplicate physical frames while retaining their canonical timestamp."""
    candidates = {
        (str(video_id), int(frame_index)): float(timestamp)
        for video_id, frame_index, timestamp in frames
    }
    return tuple(
        (video_id, frame_index, timestamp)
        for (video_id, frame_index), timestamp in sorted(candidates.items())
    )


def _copy_repeat_details(
    details: dict[FrameKey, RepeatFrameDetails],
) -> dict[FrameKey, RepeatFrameDetails]:
    """Prevent callers from mutating the cached response structure."""
    copied: dict[FrameKey, RepeatFrameDetails] = {}
    for key, witnesses in details.items():
        copied_witnesses: RepeatFrameDetails = {}
        highest = witnesses.get("in_video_highest_duplicate")
        if highest is not None:
            copied_witnesses["in_video_highest_duplicate"] = {
                "video_id": highest["video_id"],
                "frame_index": highest["frame_index"],
            }
        furthest = witnesses.get("in_video_furthest_duplicate")
        if furthest is not None:
            copied_witnesses["in_video_furthest_duplicate"] = {
                "video_id": furthest["video_id"],
                "frame_index": furthest["frame_index"],
            }
        outside = witnesses.get("out_video_highest_duplicate")
        if outside is not None:
            copied_witnesses["out_video_highest_duplicate"] = {
                "video_id": outside["video_id"],
                "frame_index": outside["frame_index"],
            }
        copied[key] = copied_witnesses
    return copied


def _cache_get(
    cache_key: tuple[str, tuple[RepeatCandidate, ...]],
) -> dict[FrameKey, RepeatFrameDetails] | None:
    with _cache_lock:
        result = _repeat_cache.get(cache_key)
        if result is not None:
            _repeat_cache.move_to_end(cache_key)
        return _copy_repeat_details(result) if result is not None else None


def _cache_put(
    cache_key: tuple[str, tuple[RepeatCandidate, ...]], result: dict[FrameKey, RepeatFrameDetails]
) -> None:
    with _cache_lock:
        _repeat_cache[cache_key] = _copy_repeat_details(result)
        _repeat_cache.move_to_end(cache_key)
        while len(_repeat_cache) > _CACHE_LIMIT:
            _repeat_cache.popitem(last=False)


def _valid_embedding_rows(
    candidates: Sequence[RepeatCandidate], embeddings: dict[FrameKey, list[float]]
) -> tuple[list[RepeatCandidate], np.ndarray]:
    rows: list[np.ndarray] = []
    available_candidates: list[RepeatCandidate] = []
    expected_dimension: int | None = None
    for video_id, frame_index, timestamp in candidates:
        key = (video_id, frame_index)
        raw = embeddings.get(key)
        if raw is None:
            continue
        vector = np.asarray(raw, dtype=np.float32)
        if vector.ndim != 1 or not np.isfinite(vector).all():
            continue
        if expected_dimension is None:
            expected_dimension = int(vector.shape[0])
        if vector.shape[0] != expected_dimension:
            continue
        available_candidates.append((video_id, frame_index, timestamp))
        rows.append(vector)
    if not rows:
        return [], np.empty((0, 0), dtype=np.float32)
    return available_candidates, np.vstack(rows)


def _reference(candidate: RepeatCandidate) -> RepeatFrameReference:
    return {"video_id": candidate[0], "frame_index": candidate[1]}


def _repeat_details_by_row(
    vectors: np.ndarray, candidates: Sequence[RepeatCandidate], threshold: float
) -> dict[int, RepeatFrameDetails]:
    """Select repeat witnesses while each bounded cosine block is in memory."""
    details_by_row: dict[int, RepeatFrameDetails] = {}
    total = vectors.shape[0]
    video_ids = np.asarray([candidate[0] for candidate in candidates])
    frame_indices = np.asarray([candidate[1] for candidate in candidates], dtype=np.int64)
    timestamps = np.asarray([candidate[2] for candidate in candidates], dtype=np.float64)
    is_l25 = np.char.startswith(video_ids.astype(str), "L25_")
    for start in range(0, total, _MATRIX_BLOCK_SIZE):
        end = min(total, start + _MATRIX_BLOCK_SIZE)
        similarities = vectors[start:end] @ vectors.T
        same_video = video_ids[start:end, None] == video_ids[None, :]
        same_group = is_l25[start:end, None] == is_l25[None, :]
        min_gap = np.where(
            is_l25[start:end, None],
            L25_SAME_VIDEO_MIN_TIMESTAMP_GAP_SECONDS,
            SAME_VIDEO_MIN_TIMESTAMP_GAP_SECONDS,
        )
        close_same_video = same_video & (
            np.abs(timestamps[start:end, None] - timestamps[None, :])
            < min_gap
        )
        similarities[~same_group | close_same_video] = -np.inf
        required_threshold = np.where(
            is_l25[start:end, None], L25_REPEAT_SIMILARITY_THRESHOLD, threshold
        )
        eligible = similarities >= required_threshold - SIMILARITY_COMPARISON_EPSILON
        for local_row in range(end - start):
            candidate_indices = np.flatnonzero(eligible[local_row])
            if candidate_indices.size == 0:
                continue
            row_index = start + local_row
            source = candidates[row_index]
            source_frame_index = int(frame_indices[row_index])
            witnesses: RepeatFrameDetails = {}

            in_video = [
                int(index)
                for index in candidate_indices
                if video_ids[index] == source[0]
            ]
            if in_video:
                highest = max(
                    in_video,
                    key=lambda index: (
                        float(similarities[local_row, index]),
                        abs(int(frame_indices[index]) - source_frame_index),
                        int(frame_indices[index]),
                    ),
                )
                furthest = max(
                    in_video,
                    key=lambda index: (
                        abs(int(frame_indices[index]) - source_frame_index),
                        float(similarities[local_row, index]),
                        int(frame_indices[index]),
                    ),
                )
                witnesses["in_video_highest_duplicate"] = _reference(candidates[highest])
                witnesses["in_video_furthest_duplicate"] = _reference(candidates[furthest])

            out_video = [
                int(index)
                for index in candidate_indices
                if video_ids[index] != source[0]
            ]
            if out_video:
                highest_out_video = min(
                    out_video,
                    key=lambda index: (
                        -float(similarities[local_row, index]),
                        str(video_ids[index]),
                        int(frame_indices[index]),
                    ),
                )
                witnesses["out_video_highest_duplicate"] = _reference(
                    candidates[highest_out_video]
                )
            details_by_row[row_index] = witnesses
    return details_by_row


def find_repeat_frame_details(
    frames: Sequence[RepeatCandidate],
) -> dict[FrameKey, RepeatFrameDetails]:
    """Find requested frames and their selected visual near-duplicate witnesses."""
    candidates = _canonical_candidates(frames)
    if not candidates:
        return {}
    if len(candidates) > MAX_REPEAT_FRAMES:
        raise ValueError(f"repeat detection supports at most {MAX_REPEAT_FRAMES} frames")

    graph = get_repeat_graph()
    if graph is not None:
        cache_key = (graph.cache_key, candidates)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
        graph_result = graph.find_repeat_frame_details(
            [(video_id, frame_index) for video_id, frame_index, _timestamp in candidates]
        )
        _cache_put(cache_key, graph_result)
        return _copy_repeat_details(graph_result)

    if len(candidates) < 2:
        return {}
    collection = manager.active_collection_name()
    cache_key = (f"milvus:{collection}", candidates)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    embeddings = get_milvus_client(collection).query_frame_embeddings(
        [(video_id, frame_index) for video_id, frame_index, _timestamp in candidates]
    )
    available_candidates, vectors = _valid_embedding_rows(candidates, embeddings)
    result: dict[FrameKey, RepeatFrameDetails]
    if len(available_candidates) < 2:
        result = {}
    else:
        details_by_row = _repeat_details_by_row(
            vectors, available_candidates, REPEAT_SIMILARITY_THRESHOLD
        )
        result = {
            (available_candidates[index][0], available_candidates[index][1]): details
            for index, details in details_by_row.items()
        }
    _cache_put(cache_key, result)
    return _copy_repeat_details(result)


def find_repeat_frame_keys(frames: Sequence[RepeatCandidate]) -> set[FrameKey]:
    """Compatibility wrapper for callers that need only repeated frame identities."""
    return set(find_repeat_frame_details(frames))
