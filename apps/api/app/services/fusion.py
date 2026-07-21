from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.frame_identity import frame_uid

FrameData = dict[str, Any]


@dataclass(frozen=True)
class RankedSource:
    """One ranked result list participating in reciprocal-rank fusion."""

    source_id: str
    results: Sequence[Mapping[str, Any]]
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id is required")
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("source weight must be a positive finite number")


def reciprocal_rank_fusion(
    sources: Sequence[RankedSource],
    *,
    rrf_k: int = 60,
) -> list[FrameData]:
    """Fuse independent rankings without assuming calibrated similarity scores."""
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")

    fused: dict[str, FrameData] = {}
    best_rank: dict[str, int] = {}
    for source in sources:
        seen_in_source: set[str] = set()
        unique_rank = 0
        model_id = source.source_id.split(":", maxsplit=1)[0]
        for raw_frame in source.results:
            uid = frame_uid(raw_frame)
            if uid in seen_in_source:
                continue
            seen_in_source.add(uid)
            unique_rank += 1

            contribution = source.weight / (rrf_k + unique_rank)
            if uid not in fused:
                item = dict(raw_frame)
                item["frame_uid"] = uid
                item["fusion_score"] = 0.0
                item["score"] = 0.0
                item["source_ranks"] = {}
                item["source_scores"] = {}
                item["model_ranks"] = {}
                item["model_scores"] = {}
                fused[uid] = item
                best_rank[uid] = unique_rank

            item = fused[uid]
            item["fusion_score"] = float(item["fusion_score"]) + contribution
            item["score"] = item["fusion_score"]
            item["source_ranks"][source.source_id] = unique_rank
            raw_score = float(raw_frame.get("vector_score", raw_frame.get("score", 0.0)))
            item["source_scores"][source.source_id] = raw_score
            current_model_rank = item["model_ranks"].get(model_id)
            if current_model_rank is None or unique_rank < current_model_rank:
                item["model_ranks"][model_id] = unique_rank
                item["model_scores"][model_id] = raw_score
            best_rank[uid] = min(best_rank[uid], unique_rank)

    return sorted(
        fused.values(),
        key=lambda frame: (
            -float(frame["fusion_score"]),
            best_rank[str(frame["frame_uid"])],
            str(frame["frame_uid"]),
        ),
    )


def diversify_frames(
    frames: Sequence[Mapping[str, Any]],
    *,
    min_time_gap_seconds: float = 0.0,
    max_per_video: int = 0,
    limit: int | None = None,
) -> list[FrameData]:
    """Keep ranking order while suppressing redundant results from the same Video."""
    if min_time_gap_seconds < 0:
        raise ValueError("min_time_gap_seconds cannot be negative")
    if max_per_video < 0:
        raise ValueError("max_per_video cannot be negative")

    selected: list[FrameData] = []
    selected_times: defaultdict[str, list[float]] = defaultdict(list)
    video_counts: defaultdict[str, int] = defaultdict(int)
    for raw_frame in frames:
        video_id = str(raw_frame.get("video_id", ""))
        pts_time = float(raw_frame.get("pts_time", raw_frame.get("timestamp", 0.0)) or 0.0)
        if max_per_video and video_counts[video_id] >= max_per_video:
            continue
        if min_time_gap_seconds and any(
            abs(pts_time - existing) < min_time_gap_seconds
            for existing in selected_times[video_id]
        ):
            continue

        frame = dict(raw_frame)
        frame["frame_uid"] = frame_uid(frame)
        selected.append(frame)
        selected_times[video_id].append(pts_time)
        video_counts[video_id] += 1
        if limit is not None and len(selected) >= limit:
            break
    return selected
