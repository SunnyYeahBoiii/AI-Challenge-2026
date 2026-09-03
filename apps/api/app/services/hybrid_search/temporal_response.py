"""Structured video/sequence response building for temporal search."""

import math
from collections.abc import Callable, Sequence
from typing import Any

from app.services.encoders import manager
from app.services.hybrid_search.common import (
    Box,
    Frame,
    FrameKey,
    _enrich_frames,
    _frame_index,
    _frame_key,
    _retrieval_rank,
    _similarity,
    _sorted_unique,
    _timestamp,
)
from app.services.hybrid_search.retrieval import (
    _box_vectors,
    _parallel_retrieve,
    _sequential_retrieve,
)
from app.services.hybrid_search.temporal_paths import _backward_flags, _best_path, _forward_flags


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


def add_text_display_scores(
    response: dict[str, Any],
    text_query_indices: set[int],
    calibrate: Callable[[float], float | None],
) -> None:
    """Attach optional display-only confidence to text-result frames.

    Raw cosine similarity is not comparable across encoders, so a model that can
    map it onto a calibrated probability exposes that through
    `Encoder.calibrate_text_similarity`. The calibrated number is display-only —
    ranking still uses the raw similarity, and image-query frames get nothing
    because the calibration is fitted on text-image pairs.
    """
    if not text_query_indices:
        return

    def add_score(frame: Frame) -> None:
        if bool(frame.get("filter_only")):
            return
        raw_score = _similarity(frame)
        if raw_score <= 0.0:
            return
        matches = frame.get("matches")
        if isinstance(matches, list):
            source_indices = {
                int(match.get("query_index", -1))
                for match in matches
                if isinstance(match, dict)
                and math.isclose(float(match.get("similarity", 0.0)), raw_score)
            }
        else:
            source_indices = {int(frame.get("query_index", -1))}
        if not source_indices.intersection(text_query_indices):
            return
        display_score = calibrate(raw_score)
        if display_score is None or not math.isfinite(display_score):
            return
        frame["display_score"] = display_score
        frame["display_score_kind"] = "siglip2_text_confidence"

    for video in response.get("videos", []):
        for frame in video.get("valid_frames", []):
            add_score(frame)
        for frame in video.get("best_sequence", {}).get("frames", []):
            add_score(frame)


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
    response = build_temporal_response(per_box, temporal_window, mode)
    if manager.get_status()["model_id"] == "siglip2":
        text_query_indices = {
            index
            for index, box in enumerate(box_queries)
            if bool(str(box.get("text") or "").strip())
        }
        add_text_display_scores(
            response, text_query_indices, manager.calibrate_active_text_similarity
        )
    return response
