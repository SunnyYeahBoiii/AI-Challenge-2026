"""
Index OCR/ASR text from concatenate-data.json into Elasticsearch only.

Usage:
    cd apps/api
    uv run python scripts/index_es.py --batch 1
    uv run python scripts/index_es.py --batch 1 --limit 100
    uv run python scripts/index_es.py --all --recreate
    uv run python scripts/index_es.py --batch 1 --dry-run

Expects .env in apps/api/ with ES_URL (and optional ES_USER/ES_PASS).
Data: data/Data/Batch{1,2}/concatenate-data.json
  - ocr_text  -> ES ocr_text
  - audio_text -> ES asr_text
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

# Allow `uv run python scripts/index_es.py` to import sibling helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from es_common import (  # noqa: E402
    ES_BATCH,
    bulk_insert_es,
    connect_elasticsearch,
    ensure_es_index,
    finalize_es_index,
    frame_doc_from_record,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data"
BATCH_DIRS = {
    1: DATA_ROOT / "Data" / "Batch1",
}


def index_batch(
    batch_dir: Path,
    es: Elasticsearch | None,
    *,
    index: str = "",
    limit: int | None = None,
    dry_run: bool = False,
) -> int:
    json_path = batch_dir / "concatenate-data.json"
    if not json_path.exists():
        print(f"JSON not found: {json_path}")
        return 0

    print(f"\nIndexing ES from {batch_dir.name}...")
    print(f"  JSON: {json_path}")
    with open(json_path, encoding="utf-8") as f:
        records = json.load(f)
    print(f"  Loaded {len(records)} records.")

    if dry_run:
        sample = next((frame_doc_from_record(r) for r in records if r.get("file_path")), None)
        print(f"  Dry-run sample doc: {sample}")
        n = min(limit, len(records)) if limit else len(records)
        print(f"  Would index {n} docs.")
        return n

    if es is None:
        raise ValueError("Elasticsearch client required when not dry-run")

    buffer: list[dict[str, object]] = []
    count = 0
    t0 = time.time()

    for record in records:
        if limit is not None and count >= limit:
            break
        doc = frame_doc_from_record(record)
        if doc is None:
            continue
        buffer.append(doc)
        count += 1
        if len(buffer) >= ES_BATCH:
            bulk_insert_es(es, buffer, index=index)
            buffer = []
            print(f"  [{count}] indexed...")

    if buffer:
        bulk_insert_es(es, buffer, index=index)

    elapsed = time.time() - t0
    print(f"  Done: {count} docs in {elapsed:.1f}s")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index OCR/ASR frame text into Elasticsearch (no Milvus)"
    )
    parser.add_argument("--batch", type=int, choices=[1], help="Load specific batch")
    parser.add_argument("--all", action="store_true", help="Load both batches")
    parser.add_argument("--limit", type=int, help="Max records to index")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; skip ES writes")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the video_texts index before indexing",
    )
    args = parser.parse_args()

    if not args.all and args.batch is None:
        parser.error("Specify --batch 1 or --all")

    dirs = list(BATCH_DIRS.values()) if args.all else [BATCH_DIRS[args.batch]]

    es: Elasticsearch | None = None
    target_index = ""
    if not args.dry_run:
        es = connect_elasticsearch()
        target_index = ensure_es_index(es, recreate=args.recreate)

    total = 0
    for batch_dir in dirs:
        total += index_batch(
            batch_dir, es, index=target_index, limit=args.limit, dry_run=args.dry_run
        )
    print(f"\nTotal indexed: {total}")

    if es is not None and target_index:
        finalize_es_index(es, target_index)


if __name__ == "__main__":
    main()
