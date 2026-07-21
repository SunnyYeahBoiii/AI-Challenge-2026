"""Generate per-model retrieval rankings for reproducible ensemble ablations."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from app.services.embedding_artifacts import iter_input_records
from app.services.frame_identity import frame_uid
from app.services.milvus_client import get_vector_backend
from app.services.model_registry import ModelRegistry, load_model_specs


def _queries(path: Path) -> list[dict[str, Any]]:
    queries = list(iter_input_records(path))
    for query in queries:
        if not str(query.get("query_id", "")) or not str(query.get("text", "")):
            raise ValueError("each Query requires query_id and text")
    return queries


def generate_runs(
    *,
    queries: list[dict[str, Any]],
    registry: ModelRegistry,
    model_ids: list[str],
    top_k: int,
    query_batch_size: int,
) -> list[dict[str, Any]]:
    """Encode a fixed Query set with each model and preserve independent rankings."""
    if top_k < 1 or query_batch_size < 1:
        raise ValueError("top_k and query_batch_size must be positive")
    run_records = {
        str(query["query_id"]): {
            "query_id": str(query["query_id"]),
            "text": str(query["text"]),
            "query_class": query.get("query_class", ""),
            "rankings": {},
            "latency_ms": {},
        }
        for query in queries
    }
    backend = get_vector_backend()
    for model_id in model_ids:
        spec = registry.spec(model_id)
        try:
            model = registry.get(model_id)
            for start in range(0, len(queries), query_batch_size):
                batch = queries[start : start + query_batch_size]
                texts = [str(query["text"]) for query in batch]
                encode_started = time.perf_counter()
                embeddings = model.encode_texts(texts)
                encode_elapsed_ms = (time.perf_counter() - encode_started) * 1_000
                per_query_encode_ms = encode_elapsed_ms / len(batch)
                for query, embedding in zip(batch, embeddings):
                    search_started = time.perf_counter()
                    frames = backend.search(spec, embedding.tolist(), top_k)
                    search_elapsed_ms = (time.perf_counter() - search_started) * 1_000
                    query_id = str(query["query_id"])
                    run_records[query_id]["rankings"][model_id] = [
                        frame_uid(frame) for frame in frames
                    ]
                    run_records[query_id]["latency_ms"][model_id] = {
                        "encode": per_query_encode_ms,
                        "search": search_elapsed_ms,
                    }
        finally:
            registry.unload(model_id)
    return list(run_records.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "ensemble.json",
    )
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--top-k", type=int, default=1_000)
    parser.add_argument("--query-batch-size", type=int, default=64)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = ModelRegistry(load_model_specs(args.config))
    model_ids = args.models or [spec.model_id for spec in registry.enabled_specs()]
    records = generate_runs(
        queries=_queries(args.queries),
        registry=registry,
        model_ids=model_ids,
        top_k=args.top_k,
        query_batch_size=args.query_batch_size,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
