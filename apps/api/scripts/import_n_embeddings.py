"""Validate and append N-series BEIT-3 embedding shards to Milvus.

The N corpus is stored as paired ``n-*-records-*.jsonl`` and
``n-*-embeddings-*.npy`` shards. This loader is idempotent: frame keys already
present in the target collection are skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from pymilvus import Collection, connections, utility

API_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = API_ROOT.parent.parent
load_dotenv(API_ROOT / ".env")
sys.path.insert(0, str(API_ROOT))

from app.services.video_id import level_of  # noqa: E402

EMBEDDING_DIM = 1024
MILVUS_BATCH = 8_000
TAG_ITEM_MAX_LEN = 32
TAGS_MAX_COUNT = 100
FrameKey = tuple[str, int]


def canonical_frame_path(video_id: str, frame_index: int) -> str:
    """Return the repository-relative N-series keyframe path."""
    return f"keyframes/{level_of(video_id)}/{video_id}/{frame_index}.webp"


def embedding_path_for_record(record_path: Path, embeddings_dir: Path) -> Path:
    """Map a record shard filename to its index-aligned embedding shard."""
    name = record_path.name.replace("-records-", "-embeddings-")
    return embeddings_dir / f"{Path(name).stem}.npy"


def iter_embedding_shards(
    records_dir: Path, embeddings_dir: Path
) -> Iterator[tuple[Path, Path]]:
    """Yield every N record shard with its required embedding partner."""
    record_paths = sorted(records_dir.glob("n-*-records-*.jsonl"))
    if not record_paths:
        raise FileNotFoundError(f"No N record shards found in {records_dir}")
    for record_path in record_paths:
        embedding_path = embedding_path_for_record(record_path, embeddings_dir)
        if not embedding_path.is_file():
            raise FileNotFoundError(f"Embedding shard not found: {embedding_path}")
        yield record_path, embedding_path


def _read_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _frame_index(record: dict[str, Any]) -> int:
    value = record.get("frame_index")
    if value is None:
        value = record.get("frame_idx")
    if value is None:
        raise ValueError(f"Missing frame index in record: {record}")
    return int(value)


def validate_artifacts(
    records_dir: Path, embeddings_dir: Path, keyframes_dir: Path
) -> int:
    """Validate shard alignment, dimensions, identities, and local keyframes."""
    seen: set[FrameKey] = set()
    for record_path, embedding_path in iter_embedding_shards(records_dir, embeddings_dir):
        records = _read_records(record_path)
        embeddings = np.load(embedding_path, mmap_mode="r", allow_pickle=False)
        if len(records) != len(embeddings):
            raise ValueError(
                f"Row mismatch for {record_path.name}: {len(records)} records vs "
                f"{len(embeddings)} embeddings"
            )
        if embeddings.ndim != 2 or embeddings.shape[1] != EMBEDDING_DIM:
            raise ValueError(f"Unexpected embedding shape in {embedding_path}: {embeddings.shape}")
        for record in records:
            video_id = str(record.get("video_id") or "")
            if not video_id.startswith("N"):
                raise ValueError(f"Non-N video in {record_path}: {video_id!r}")
            frame_index = _frame_index(record)
            key = (video_id, frame_index)
            if key in seen:
                raise ValueError(f"Duplicate N frame: {video_id}:{frame_index}")
            seen.add(key)
            keyframe = keyframes_dir / level_of(video_id) / video_id / f"{frame_index}.webp"
            if not keyframe.is_file():
                raise FileNotFoundError(f"Missing keyframe: {keyframe}")
    return len(seen)


def _existing_n_keys(collection: Collection) -> set[FrameKey]:
    keys: set[FrameKey] = set()
    iterator = collection.query_iterator(
        batch_size=1_000,
        expr='video_id like "N%"',
        output_fields=["video_id", "frame_index"],
    )
    try:
        while batch := iterator.next():
            keys.update((str(row["video_id"]), int(row["frame_index"])) for row in batch)
    finally:
        iterator.close()
    return keys


def _empty_buffer() -> list[list[object]]:
    return [[] for _ in range(14)]


def _append_row(
    buffer: list[list[object]], record: dict[str, Any], embedding: np.ndarray[Any, Any]
) -> None:
    video_id = str(record["video_id"])
    frame_index = _frame_index(record)
    timestamp = float(record.get("timestamp") or record.get("pts_time") or 0.0)
    tags = [str(tag)[:TAG_ITEM_MAX_LEN] for tag in (record.get("tags") or [])]
    buffer[0].append(video_id)
    buffer[1].append(str(record.get("video_path") or video_id).rstrip("/"))
    buffer[2].append(str(record.get("youtube_url") or ""))
    buffer[3].append(frame_index)
    buffer[4].append(frame_index)
    buffer[5].append(canonical_frame_path(video_id, frame_index))
    buffer[6].append(int(record.get("shot_idx") or 0))
    buffer[7].append(float(record.get("start_time") or timestamp))
    buffer[8].append(float(record.get("end_time") or timestamp))
    buffer[9].append(float(record.get("pts_time") or timestamp))
    buffer[10].append(float(record.get("fps") or 0.0))
    buffer[11].append(timestamp)
    buffer[12].append(tags[:TAGS_MAX_COUNT])
    buffer[13].append(embedding.astype(np.float32).tolist())


def load_milvus(records_dir: Path, embeddings_dir: Path, collection_name: str) -> int:
    """Append N vectors missing from an existing Milvus collection."""
    connections.connect(
        alias="default",
        uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
        token=os.getenv("MILVUS_TOKEN", ""),
    )
    if not utility.has_collection(collection_name):
        raise ValueError(f"Milvus collection does not exist: {collection_name}")
    collection = Collection(collection_name)
    existing = _existing_n_keys(collection)
    print(f"Existing N frame keys: {len(existing)}")

    inserted = 0
    buffer = _empty_buffer()
    for record_path, embedding_path in iter_embedding_shards(records_dir, embeddings_dir):
        records = _read_records(record_path)
        embeddings = np.load(embedding_path, mmap_mode="r", allow_pickle=False)
        for record, embedding in zip(records, embeddings, strict=True):
            key = (str(record.get("video_id") or ""), _frame_index(record))
            if key in existing:
                continue
            _append_row(buffer, record, embedding)
            existing.add(key)
            inserted += 1
            if len(buffer[0]) >= MILVUS_BATCH:
                collection.insert(buffer)
                buffer = _empty_buffer()
                print(f"  [{inserted}] vectors inserted")
    if buffer[0]:
        collection.insert(buffer)
    collection.flush()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Import N-series BEIT-3 embeddings")
    parser.add_argument("stage", choices=["validate", "milvus"])
    parser.add_argument("--records-dir", type=Path, default=REPO_ROOT / "data/media-info")
    parser.add_argument("--embeddings-dir", type=Path, default=REPO_ROOT / "data/embeddings")
    parser.add_argument("--keyframes-dir", type=Path, default=REPO_ROOT / "data/keyframes")
    parser.add_argument("--collection", default="data_frames_beit3")
    args = parser.parse_args()

    started = time.time()
    count = validate_artifacts(args.records_dir, args.embeddings_dir, args.keyframes_dir)
    print(f"Validated N artifacts: {count}")
    if args.stage == "milvus":
        inserted = load_milvus(args.records_dir, args.embeddings_dir, args.collection)
        print(f"Milvus vectors inserted: {inserted}")
    print(f"Done in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
