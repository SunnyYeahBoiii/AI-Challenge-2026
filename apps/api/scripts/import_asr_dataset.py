"""Import the local M/S ASR corpus into FrameSeeker.

The ASR JSON files only provide ``audio_text``. Frame ordering, shot metadata,
timestamps, and embeddings continue to come from the existing record shards so
repeated rolling ASR context remains attached to every original frame.

Usage::

    uv run python scripts/import_asr_dataset.py validate
    uv run python scripts/import_asr_dataset.py all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from pymilvus import Collection, connections, utility

API_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = API_ROOT.parent.parent
load_dotenv(API_ROOT / ".env")

# Allow this file to run directly and to reuse the existing ES schema helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from es_common import (  # noqa: E402
    ES_BATCH,
    connect_elasticsearch,
    ensure_es_index,
    finalize_es_index,
    normalize_text,
)

TARGET_PREFIXES = ("M", "S01-")
EMBEDDING_DIM = 1024
MILVUS_BATCH = 8_000
TAG_ITEM_MAX_LEN = 32
TAGS_MAX_COUNT = 100
FrameKey = tuple[str, int]


@dataclass(frozen=True, slots=True)
class AsrRecord:
    """The only ASR fields consumed by the runtime search index."""

    video_id: str
    frame_idx: int
    audio_text: str


def _is_target_video(video_id: str) -> bool:
    return video_id.startswith(TARGET_PREFIXES)


def canonical_frame_path(video_id: str, frame_idx: int) -> str:
    """Return the repository-relative keyframe path used by the API."""
    return f"keyframes/{video_id[:3]}/{video_id}/{frame_idx}.webp"


def load_asr_records(asr_dir: Path) -> dict[FrameKey, AsrRecord]:
    """Load M/S ASR recursively while retaining repeated text on every frame."""
    if not asr_dir.is_dir():
        raise FileNotFoundError(f"ASR directory not found: {asr_dir}")

    records: dict[FrameKey, AsrRecord] = {}
    for json_path in sorted(asr_dir.rglob("*.json")):
        if not _is_target_video(json_path.stem):
            continue
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Expected a JSON array in {json_path}")
        for raw in payload:
            video_id = str(raw.get("video_id") or "")
            if video_id != json_path.stem:
                raise ValueError(
                    f"video_id {video_id!r} does not match file {json_path.stem!r}"
                )
            if not _is_target_video(video_id):
                continue
            if raw.get("frame_idx") is None:
                raise ValueError(f"Missing frame_idx in {json_path}")
            frame_idx = int(raw["frame_idx"])
            key = (video_id, frame_idx)
            if key in records:
                raise ValueError(f"Duplicate ASR frame: {video_id}:{frame_idx}")
            records[key] = AsrRecord(
                video_id=video_id,
                frame_idx=frame_idx,
                audio_text=str(raw.get("audio_text") or ""),
            )
    if not records:
        raise ValueError(f"No M/S ASR records found under {asr_dir}")
    return records


def asr_document(record: AsrRecord) -> dict[str, object]:
    """Build a partial ES document without touching any existing OCR text."""
    frame_path = canonical_frame_path(record.video_id, record.frame_idx)
    return {
        "frame_key": f"{record.video_id}:{record.frame_idx}",
        "video_id": record.video_id,
        "video_path": str(Path(frame_path).parent),
        "frame_id": record.frame_idx,
        "frame_idx": record.frame_idx,
        "frame_path": frame_path,
        "asr_text": normalize_text(record.audio_text),
    }


def build_es_bulk_body(
    records: Iterable[AsrRecord], index: str
) -> list[dict[str, object]]:
    """Build partial-update actions so a rerun preserves existing OCR fields."""
    body: list[dict[str, object]] = []
    for record in records:
        document = asr_document(record)
        body.append({"update": {"_index": index, "_id": document["frame_key"]}})
        body.append({"doc": document, "doc_as_upsert": True})
    return body


def embedding_path_for_record(record_path: Path, embeddings_dir: Path) -> Path:
    """Map one ``records`` shard name to its index-aligned embedding shard."""
    name = record_path.name.replace("-records-", "-embeddings-")
    if name == record_path.name:
        name = name.replace("records-", "embeddings-", 1)
    return embeddings_dir / f"{Path(name).stem}.npy"


def iter_embedding_shards(
    records_dir: Path, embeddings_dir: Path
) -> Iterator[tuple[Path, Path]]:
    """Yield the M/S record shards and their required embedding partners."""
    record_paths = sorted(records_dir.glob("ms-*-records-*.jsonl"))
    if not record_paths:
        raise FileNotFoundError(f"No M/S record shards found in {records_dir}")
    for record_path in record_paths:
        embedding_path = embedding_path_for_record(record_path, embeddings_dir)
        if not embedding_path.is_file():
            raise FileNotFoundError(f"Embedding shard not found: {embedding_path}")
        yield record_path, embedding_path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def validate_artifacts(
    asr_records: dict[FrameKey, AsrRecord],
    records_dir: Path,
    embeddings_dir: Path,
) -> int:
    """Validate row alignment, dimensions, uniqueness, and ASR/vector key parity."""
    vector_keys: set[FrameKey] = set()
    total = 0
    for record_path, embedding_path in iter_embedding_shards(records_dir, embeddings_dir):
        frame_records = _read_jsonl(record_path)
        embeddings = np.load(embedding_path, mmap_mode="r", allow_pickle=False)
        if len(frame_records) != len(embeddings):
            raise ValueError(
                f"Row mismatch for {record_path.name}: {len(frame_records)} records vs "
                f"{len(embeddings)} embeddings"
            )
        if embeddings.ndim != 2 or embeddings.shape[1] != EMBEDDING_DIM:
            raise ValueError(f"Unexpected embedding shape in {embedding_path}: {embeddings.shape}")
        for raw in frame_records:
            video_id = str(raw.get("video_id") or "")
            if not _is_target_video(video_id):
                continue
            frame_idx = _frame_index(raw)
            key = (video_id, frame_idx)
            if key in vector_keys:
                raise ValueError(f"Duplicate vector frame: {video_id}:{frame_idx}")
            vector_keys.add(key)
            total += 1

    asr_keys = set(asr_records)
    if vector_keys != asr_keys:
        missing_vectors = sorted(asr_keys - vector_keys)[:3]
        missing_asr = sorted(vector_keys - asr_keys)[:3]
        raise ValueError(
            "ASR/vector key mismatch: "
            f"missing vectors={missing_vectors}, missing ASR={missing_asr}"
        )
    return total


def validate_media(asr_records: dict[FrameKey, AsrRecord], video_dir: Path) -> None:
    """Require one local MP4 for every selected M/S video."""
    missing = sorted(
        video_id
        for video_id in {key[0] for key in asr_records}
        if not (video_dir / f"{video_id}.mp4").is_file()
    )
    if missing:
        raise FileNotFoundError(f"Missing source videos: {missing[:5]}")


def validate_keyframes(
    asr_records: dict[FrameKey, AsrRecord], keyframes_dir: Path
) -> None:
    """Require one existing local keyframe for every selected ASR record."""
    missing = [
        canonical_frame_path(video_id, frame_idx)
        for video_id, frame_idx in asr_records
        if not (keyframes_dir / video_id[:3] / video_id / f"{frame_idx}.webp").is_file()
    ]
    if missing:
        raise FileNotFoundError(f"Missing keyframes: {missing[:5]}")


def _frame_index(record: dict[str, Any]) -> int:
    value = record.get("frame_idx")
    if value is None:
        value = record.get("frame_index")
    if value is None:
        raise ValueError(f"Missing frame index in record: {record}")
    return int(value)


def _existing_milvus_keys(collection: Collection, video_ids: Iterable[str]) -> set[FrameKey]:
    keys: set[FrameKey] = set()
    for video_id in sorted(set(video_ids)):
        iterator = collection.query_iterator(
            batch_size=1_000,
            expr=f'video_id == "{video_id}"',
            output_fields=["video_id", "frame_index"],
        )
        try:
            while batch := iterator.next():
                keys.update((str(row["video_id"]), int(row["frame_index"])) for row in batch)
        finally:
            iterator.close()
    return keys


def _milvus_buffer() -> list[list[object]]:
    return [[] for _ in range(14)]


def _append_milvus_row(
    buffer: list[list[object]], record: dict[str, Any], embedding: np.ndarray[Any, Any]
) -> None:
    video_id = str(record["video_id"])
    frame_idx = _frame_index(record)
    tags = [str(tag)[:TAG_ITEM_MAX_LEN] for tag in (record.get("tags") or [])]
    tags = tags[:TAGS_MAX_COUNT]
    timestamp = float(record.get("timestamp") or record.get("pts_time") or 0.0)
    buffer[0].append(video_id)
    buffer[1].append(str(record.get("video_path") or video_id).rstrip("/"))
    buffer[2].append(str(record.get("youtube_url") or ""))
    buffer[3].append(frame_idx)
    buffer[4].append(frame_idx)
    buffer[5].append(canonical_frame_path(video_id, frame_idx))
    buffer[6].append(int(record.get("shot_idx") or 0))
    buffer[7].append(float(record.get("start_time") or timestamp))
    buffer[8].append(float(record.get("end_time") or timestamp))
    buffer[9].append(float(record.get("pts_time") or timestamp))
    buffer[10].append(float(record.get("fps") or 0.0))
    buffer[11].append(timestamp)
    buffer[12].append(tags)
    buffer[13].append(embedding.astype(np.float32).tolist())


def load_milvus(
    asr_records: dict[FrameKey, AsrRecord],
    records_dir: Path,
    embeddings_dir: Path,
    collection_name: str,
) -> int:
    """Append missing M/S vectors to the existing BEIT3 collection."""
    uri = os.getenv("MILVUS_URI", "http://localhost:19530")
    token = os.getenv("MILVUS_TOKEN", "")
    connections.connect(alias="default", uri=uri, token=token)
    if not utility.has_collection(collection_name):
        raise ValueError(f"Milvus collection does not exist: {collection_name}")
    collection = Collection(collection_name)
    existing = _existing_milvus_keys(collection, (key[0] for key in asr_records))
    print(f"  Existing M/S frame keys: {len(existing)}")

    inserted = 0
    buffer = _milvus_buffer()
    for record_path, embedding_path in iter_embedding_shards(records_dir, embeddings_dir):
        frame_records = _read_jsonl(record_path)
        embeddings = np.load(embedding_path, mmap_mode="r", allow_pickle=False)
        for record, embedding in zip(frame_records, embeddings, strict=True):
            video_id = str(record.get("video_id") or "")
            if not _is_target_video(video_id):
                continue
            key = (video_id, _frame_index(record))
            if key not in asr_records or key in existing:
                continue
            _append_milvus_row(buffer, record, embedding)
            existing.add(key)
            inserted += 1
            if len(buffer[0]) >= MILVUS_BATCH:
                collection.insert(buffer)
                buffer = _milvus_buffer()
                print(f"  [{inserted}] vectors inserted")
    if buffer[0]:
        collection.insert(buffer)
    collection.flush()
    return inserted


def _send_es_batch(es: Elasticsearch, records: Sequence[AsrRecord], index: str) -> None:
    response = es.bulk(body=build_es_bulk_body(records, index))
    if not response.get("errors"):
        return
    errors = [item for item in response["items"] if item.get("update", {}).get("error")]
    raise RuntimeError(f"Elasticsearch bulk update failed: {errors[:3]}")


def load_elasticsearch(asr_records: dict[FrameKey, AsrRecord]) -> int:
    """Upsert non-empty M/S ASR text without replacing any OCR field."""
    es = connect_elasticsearch()
    index = ensure_es_index(es, recreate=False)
    nonempty = [record for record in asr_records.values() if record.audio_text.strip()]
    for start in range(0, len(nonempty), ES_BATCH):
        _send_es_batch(es, nonempty[start : start + ES_BATCH], index)
        if start and start % 20_000 == 0:
            print(f"  [{start}/{len(nonempty)}] ASR documents upserted")
    finalize_es_index(es, index)
    return len(nonempty)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import local M/S ASR data")
    parser.add_argument(
        "stage", choices=["validate", "milvus", "elasticsearch", "all"]
    )
    parser.add_argument("--asr-dir", type=Path, default=REPO_ROOT / "ASR")
    parser.add_argument("--records-dir", type=Path, default=REPO_ROOT / "data/media-info")
    parser.add_argument("--embeddings-dir", type=Path, default=REPO_ROOT / "data/embeddings")
    parser.add_argument("--video-dir", type=Path, default=REPO_ROOT / "data/video")
    parser.add_argument("--keyframes-dir", type=Path, default=REPO_ROOT / "data/keyframes")
    parser.add_argument("--collection", default="data_frames_beit3")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    started = time.time()
    print(f"Loading M/S ASR from {args.asr_dir}...")
    asr_records = load_asr_records(args.asr_dir)
    nonempty = sum(bool(record.audio_text.strip()) for record in asr_records.values())
    print(f"  ASR frames: {len(asr_records)} ({nonempty} non-empty)")
    validate_media(asr_records, args.video_dir)
    validate_keyframes(asr_records, args.keyframes_dir)
    print(f"  Keyframes validated: {len(asr_records)}")
    vector_count = validate_artifacts(asr_records, args.records_dir, args.embeddings_dir)
    print(f"  Vector records validated: {vector_count}")

    if args.stage in {"milvus", "all"}:
        inserted = load_milvus(
            asr_records, args.records_dir, args.embeddings_dir, args.collection
        )
        print(f"  Milvus vectors inserted: {inserted}")
    if args.stage in {"elasticsearch", "all"}:
        indexed = load_elasticsearch(asr_records)
        print(f"  Elasticsearch documents upserted: {indexed}")
    print(f"Done in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
