"""Measure per-stage latency of the multi-box search pipeline.

Requires a live Milvus (and Elasticsearch if the queries use keywords).

    cd apps/api
    uv run python scripts/bench_search.py --model metaclip --boxes 3 --repeat 5
    uv run python scripts/bench_search.py --model beit3 --mode sequential --no-enhance
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import hybrid_search, video_meta  # noqa: E402
from app.services.encoders import manager  # noqa: E402

DEFAULT_QUERIES = [
    "a pedestrian crossing a busy street",
    "a car collision at an intersection",
    "a crowd gathering around an accident",
    "police officers directing traffic",
    "an ambulance arriving at the scene",
]


class Timer:
    """Accumulates wall-clock per named stage and counts the calls."""

    def __init__(self):
        self.samples: dict[str, list[float]] = {}

    def record(self, stage: str, seconds: float) -> None:
        self.samples.setdefault(stage, []).append(seconds)

    def wrap(self, module, name, stage):
        original = getattr(module, name)

        def wrapped(*args, **kwargs):
            start = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.record(stage, time.perf_counter() - start)

        setattr(module, name, wrapped)
        return original

    def report(self) -> None:
        width = max((len(s) for s in self.samples), default=10)
        print(f"\n{'stage'.ljust(width)}  calls    p50 ms    p95 ms   total ms")
        print("-" * (width + 40))
        for stage, values in sorted(self.samples.items(), key=lambda kv: -sum(kv[1])):
            ms = sorted(v * 1000 for v in values)
            p50 = statistics.median(ms)
            p95 = ms[min(len(ms) - 1, int(len(ms) * 0.95))]
            print(
                f"{stage.ljust(width)}  {len(ms):5d}  {p50:8.1f}  {p95:8.1f}  {sum(ms):9.1f}"
            )


def instrument(timer: Timer) -> None:
    timer.wrap(hybrid_search, "enhance_queries", "enhance")
    timer.wrap(manager, "embed_text", "embed_text")
    timer.wrap(manager, "embed_images", "embed_images")
    timer.wrap(hybrid_search, "_grouped_search", "milvus")
    timer.wrap(hybrid_search, "_filter_by_keywords", "es_keywords")
    timer.wrap(hybrid_search, "_enrich_frames", "enrich")
    timer.wrap(hybrid_search, "merge_rrf", "merge_rrf")
    timer.wrap(hybrid_search, "merge_temporal", "merge_temporal")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=manager.list_models())
    parser.add_argument("--boxes", type=int, default=3)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--topk", type=int, default=200)
    parser.add_argument("--mode", choices=["parallel", "sequential"], default="parallel")
    parser.add_argument("--window", type=float, default=120.0)
    parser.add_argument("--no-enhance", action="store_true")
    parser.add_argument("--tags", nargs="*", default=[])
    parser.add_argument("--keywords", nargs="*", default=[])
    args = parser.parse_args()

    if args.boxes > len(DEFAULT_QUERIES):
        parser.error(f"--boxes must be <= {len(DEFAULT_QUERIES)}")

    print(f"Loaded metadata for {video_meta.load()} videos.")
    print(f"Warming up {args.model} and its Milvus collection...")
    t0 = time.perf_counter()
    manager.swap(args.model)
    print(f"Warmup: {(time.perf_counter() - t0) * 1000:.0f} ms")

    boxes = [
        {
            "text": DEFAULT_QUERIES[i],
            "tags": args.tags,
            "keywords": args.keywords,
            "tag_match_mode": "and",
            "key_match_mode": "and",
            "keyword_source": "all",
            "enhance": None,
        }
        for i in range(args.boxes)
    ]

    timer = Timer()
    instrument(timer)

    totals = []
    for run in range(args.repeat):
        start = time.perf_counter()
        results = hybrid_search.multi_box_search(
            box_queries=boxes,
            temporal_window=args.window,
            topk=args.topk,
            enhance=not args.no_enhance,
            mode=args.mode,
        )
        elapsed = time.perf_counter() - start
        totals.append(elapsed)
        print(f"run {run + 1}/{args.repeat}: {elapsed * 1000:8.1f} ms  {len(results)} results")

    timer.report()
    ms = sorted(t * 1000 for t in totals)
    print(
        f"\nend-to-end  p50 {statistics.median(ms):.1f} ms  "
        f"min {ms[0]:.1f} ms  max {ms[-1]:.1f} ms"
    )
    print(
        "note: run 1 includes cold caches (enhance LRU, Milvus segment load); "
        "compare run 2+ when judging steady-state latency."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
