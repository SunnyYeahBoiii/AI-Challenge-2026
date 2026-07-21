"""Evaluate saved retrieval runs and enumerate all RRF source ablations.

Ground truth JSONL:
    {"query_id": "q1", "relevant_frame_uids": ["V1:00000001"]}

Run JSONL:
    {"query_id": "q1", "rankings": {"dfn5b": [...], "siglip2": [...]}}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.evaluation.ablation import evaluate_source_ablation
from app.services.embedding_artifacts import iter_input_records


def _load_ground_truth(path: Path) -> dict[str, set[str]]:
    ground_truth: dict[str, set[str]] = {}
    for record in iter_input_records(path):
        query_id = str(record["query_id"])
        relevant = {str(uid) for uid in record.get("relevant_frame_uids", [])}
        if not relevant:
            raise ValueError(f"Query {query_id} has no relevant_frame_uids")
        ground_truth[query_id] = relevant
    return ground_truth


def _load_runs(path: Path) -> dict[str, dict[str, list[str]]]:
    runs: dict[str, dict[str, list[str]]] = {}
    for record in iter_input_records(path):
        query_id = str(record["query_id"])
        raw_rankings = record.get("rankings", {})
        if not isinstance(raw_rankings, dict):
            raise ValueError(f"Query {query_id} rankings must be an object")
        runs[query_id] = {
            str(source): [str(uid) for uid in ranking]
            for source, ranking in raw_rankings.items()
        }
    return runs


def _load_weights(raw_weights: str | None) -> dict[str, float]:
    if not raw_weights:
        return {}
    parsed: Any = json.loads(raw_weights)
    if not isinstance(parsed, dict):
        raise ValueError("weights must be a JSON object")
    return {str(source): float(weight) for source, weight in parsed.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--weights", help='JSON object, e.g. {"dfn5b":1,"siglip2":1.2}')
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--recall-at", type=int, nargs="+", default=[1, 5, 10])
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = evaluate_source_ablation(
        _load_ground_truth(args.ground_truth),
        _load_runs(args.runs),
        source_weights=_load_weights(args.weights),
        rrf_k=args.rrf_k,
        recall_at=tuple(args.recall_at),
    )
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

