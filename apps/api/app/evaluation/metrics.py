from __future__ import annotations

from collections.abc import Mapping, Sequence, Set


def _reciprocal_rank(relevant: Set[str], ranking: Sequence[str]) -> float:
    for rank, frame_uid in enumerate(ranking, start=1):
        if frame_uid in relevant:
            return 1.0 / rank
    return 0.0


def _average_precision(relevant: Set[str], ranking: Sequence[str]) -> float:
    if not relevant:
        return 0.0
    hits = 0
    precision_sum = 0.0
    seen: set[str] = set()
    for rank, frame_uid in enumerate(ranking, start=1):
        if frame_uid in seen:
            continue
        seen.add(frame_uid)
        if frame_uid in relevant:
            hits += 1
            precision_sum += hits / rank
    return precision_sum / len(relevant)


def evaluate_rankings(
    ground_truth: Mapping[str, Set[str]],
    rankings: Mapping[str, Sequence[str]],
    *,
    recall_at: Sequence[int] = (1, 5, 10),
) -> dict[str, float | int]:
    """Compute KIS-friendly Recall@K, MRR and mAP for retrieval runs."""
    if not ground_truth:
        raise ValueError("ground_truth cannot be empty")
    if any(k < 1 for k in recall_at):
        raise ValueError("recall cutoffs must be positive")

    query_count = len(ground_truth)
    recalls = {k: 0 for k in recall_at}
    reciprocal_rank_sum = 0.0
    average_precision_sum = 0.0
    for query_id, relevant in ground_truth.items():
        ranking = rankings.get(query_id, [])
        for cutoff in recall_at:
            if any(frame_uid in relevant for frame_uid in ranking[:cutoff]):
                recalls[cutoff] += 1
        reciprocal_rank_sum += _reciprocal_rank(relevant, ranking)
        average_precision_sum += _average_precision(relevant, ranking)

    metrics: dict[str, float | int] = {"queries": query_count}
    metrics.update({f"recall@{k}": count / query_count for k, count in recalls.items()})
    metrics["mrr"] = reciprocal_rank_sum / query_count
    metrics["map"] = average_precision_sum / query_count
    return metrics

