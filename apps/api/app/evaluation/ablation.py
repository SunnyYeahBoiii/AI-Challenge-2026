from __future__ import annotations

import math
from collections.abc import Mapping, Sequence, Set
from itertools import combinations

from app.evaluation.metrics import evaluate_rankings
from app.services.fusion import RankedSource, reciprocal_rank_fusion


def fuse_query_rankings(
    source_rankings: Mapping[str, Sequence[str]],
    *,
    source_weights: Mapping[str, float] | None = None,
    rrf_k: int = 60,
) -> list[str]:
    """Fuse lightweight frame_uid runs with the same production RRF implementation."""
    weights = source_weights or {}
    sources: list[RankedSource] = []
    for source_id, ranking in source_rankings.items():
        weight = float(weights.get(source_id, 1.0))
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("source weights must be finite and non-negative")
        if weight > 0:
            sources.append(
                RankedSource(
                    source_id,
                    [{"frame_uid": frame_uid} for frame_uid in ranking],
                    weight,
                )
            )
    return [str(frame["frame_uid"]) for frame in reciprocal_rank_fusion(sources, rrf_k=rrf_k)]


def evaluate_source_ablation(
    ground_truth: Mapping[str, Set[str]],
    runs: Mapping[str, Mapping[str, Sequence[str]]],
    *,
    source_weights: Mapping[str, float] | None = None,
    rrf_k: int = 60,
    recall_at: Sequence[int] = (1, 5, 10),
) -> dict[str, dict[str, float | int]]:
    """Evaluate every non-empty model/source subset to measure ensemble contribution."""
    source_ids = sorted({source_id for query in runs.values() for source_id in query})
    if not source_ids:
        raise ValueError("runs do not contain any sources")
    if source_weights:
        unknown_weights = set(source_weights) - set(source_ids)
        if unknown_weights:
            raise ValueError(f"weights contain unknown sources: {sorted(unknown_weights)}")
        if any(
            not math.isfinite(float(weight)) or float(weight) < 0
            for weight in source_weights.values()
        ):
            raise ValueError("source weights must be finite and non-negative")
    report: dict[str, dict[str, float | int]] = {}
    for subset_size in range(1, len(source_ids) + 1):
        for subset in combinations(source_ids, subset_size):
            selected = set(subset)
            rankings = {
                query_id: fuse_query_rankings(
                    {
                        source_id: ranking
                        for source_id, ranking in runs.get(query_id, {}).items()
                        if source_id in selected
                    },
                    source_weights=(
                        {
                            source_id: weight
                            for source_id, weight in source_weights.items()
                            if source_id in selected
                        }
                        if source_weights
                        else None
                    ),
                    rrf_k=rrf_k,
                )
                for query_id in ground_truth
            }
            report["+".join(subset)] = evaluate_rankings(
                ground_truth,
                rankings,
                recall_at=recall_at,
            )
    return report
