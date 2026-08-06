"""
Load pre-computed embeddings + metadata into Milvus and Elasticsearch.

Usage:
    cd apps/api
    uv run python scripts/load_data.py
    uv run python scripts/load_data.py --limit 10 --dry-run
    uv run python scripts/load_data.py --batch 1  # Batch1 only
    uv run python scripts/load_data.py --batch 2  # Batch2 only
    uv run python scripts/load_data.py --all      # Both batches

Expects .env in apps/api/ with MILVUS_URI, ES_URL, etc.
Data files:
    - data/Data/Batch{1,2}/clip-embeddings-batch{1,2}-aic25.npy
    - data/Data/Batch{1,2}/concatenate-data.json
    - data/media-info/*.json (YouTube metadata)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from pymilvus import (
    Collection,
    DataType,
    FieldSchema,
    CollectionSchema,
    connections,
    utility,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from es_common import (  # noqa: E402
    ES_BATCH,
    bulk_insert_es,
    connect_elasticsearch,
    ensure_es_index,
    extract_frame_info,
    frame_doc_from_record,
)

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")

DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data"
BATCH1_DIR = DATA_ROOT / "Data" / "Batch1"
BATCH2_DIR = DATA_ROOT / "Data" / "Batch2"
MEDIA_DIR = DATA_ROOT / "media-info"

EMBEDDING_DIM = 1024
MILVUS_BATCH = 8000

COLLECTION_NAME = "data_frames"

TAG_ITEM_MAX_LEN = 32
TAGS_MAX_COUNT = 100

CHECKPOINT_FILE = Path(__file__).resolve().parent / ".load_checkpoint.json"


# ── Milvus ──────────────────────────────────────────────────────────────────
def connect_milvus() -> None:
    print(f"Connecting to Milvus at {MILVUS_URI}...")
    connections.connect(alias="default", uri=MILVUS_URI, token=MILVUS_TOKEN)
    print("Milvus connected.")


def ensure_milvus_collection() -> Collection:
    if utility.has_collection(COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' exists.")
        return Collection(COLLECTION_NAME)

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="video_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="video_path", dtype=DataType.VARCHAR, max_length=500),
        FieldSchema(name="youtube_url", dtype=DataType.VARCHAR, max_length=500),
        FieldSchema(name="frame_index", dtype=DataType.INT64),
        FieldSchema(name="frame_idx", dtype=DataType.INT64),
        FieldSchema(name="frame_path", dtype=DataType.VARCHAR, max_length=500),
        FieldSchema(name="shot_idx", dtype=DataType.INT64),
        FieldSchema(name="start_time", dtype=DataType.FLOAT),
        FieldSchema(name="end_time", dtype=DataType.FLOAT),
        FieldSchema(name="pts_time", dtype=DataType.FLOAT),
        FieldSchema(name="fps", dtype=DataType.FLOAT),
        FieldSchema(name="timestamp", dtype=DataType.FLOAT),
        FieldSchema(
            name="tags",
            dtype=DataType.ARRAY,
            element_type=DataType.VARCHAR,
            max_length=TAG_ITEM_MAX_LEN,
            max_capacity=TAGS_MAX_COUNT,
        ),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
    ]
    schema = CollectionSchema(fields, description="Video frames with metadata and embeddings")
    col = Collection(COLLECTION_NAME, schema)

    index_params = {"metric_type": "IP", "index_type": "AUTOINDEX", "params": {}}
    col.create_index(field_name="embedding", index_params=index_params)
    print(f"Created collection '{COLLECTION_NAME}' with index.")
    return col


# ── YouTube URL mapping ─────────────────────────────────────────────────────
def load_youtube_urls() -> dict[str, str]:
    youtube_map: dict[str, str] = {}
    if not MEDIA_DIR.exists():
        print(f"Media info directory not found: {MEDIA_DIR}")
        return youtube_map

    for json_file in MEDIA_DIR.glob("*.json"):
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            watch_url = data.get("watch_url", "")
            base_name = json_file.stem  # e.g., L21_V001
            prefix = base_name.split("_")[0]  # e.g., L21
            video_path = f"keyframes/{prefix}/{base_name}"
            youtube_map[video_path] = watch_url
        except Exception as e:
            print(f"  Error reading {json_file.name}: {e}")

    print(f"Loaded {len(youtube_map)} YouTube URL mappings.")
    return youtube_map


# ── Checkpoint ──────────────────────────────────────────────────────────────
def load_checkpoint() -> set[str]:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            data = json.load(f)
        return set(data.get("processed", []))
    return set()


def save_checkpoint(processed: set[str]) -> None:
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"processed": sorted(processed)}, f)


# ── Data loading ────────────────────────────────────────────────────────────
def load_batch(
    batch_dir: Path,
    youtube_map: dict[str, str],
    es: Elasticsearch,
    col: Collection,
    processed: set[str],
    limit: int | None = None,
    dry_run: bool = False,
) -> tuple[int, int]:
    json_path = batch_dir / "concatenate-data.json"
    npy_path = batch_dir.name.replace("Batch", "clip-embeddings-batch").lower()
    npy_file = batch_dir / f"{npy_path}-aic25.npy"

    if not json_path.exists():
        print(f"JSON not found: {json_path}")
        return 0, 0
    if not npy_file.exists():
        print(f"NPY not found: {npy_file}")
        return 0, 0

    print(f"\nLoading from {batch_dir.name}...")
    print(f"  JSON: {json_path}")
    print(f"  NPY: {npy_file}")

    with open(json_path, encoding="utf-8") as f:
        json_data = json.load(f)
    print(f"  Loaded {len(json_data)} JSON records.")

    embeddings = np.load(npy_file)
    print(f"  Loaded {len(embeddings)} embeddings with shape {embeddings.shape}.")

    if len(json_data) != len(embeddings):
        print(f"  WARNING: JSON ({len(json_data)}) and NPY ({len(embeddings)}) count mismatch!")
        min_len = min(len(json_data), len(embeddings))
        json_data = json_data[:min_len]
        embeddings = embeddings[:min_len]

    total_frames = 0
    milvus_buffer: list[list[object]] = [[] for _ in range(14)]
    es_buffer: list[dict[str, object]] = []
    t0 = time.time()
    count = 0

    for i, (record, embedding) in enumerate(zip(json_data, embeddings)):
        if limit and count >= limit:
            break

        file_path = record.get("file_path", "")
        video_path, frame_id, frame_path = extract_frame_info(file_path)

        # Skip if already processed (by file_path as unique key)
        if file_path in processed:
            continue

        # Extract metadata
        key_info = record.get("keyframe_info", {})
        video_id = record.get("video_path", "").split("/")[-1]  # e.g., L21_V001
        frame_idx = int(key_info.get("frame_idx", 0))
        shot_idx = int(key_info.get("shot_idx", 0))
        start_time = float(key_info.get("start_time", 0.0))
        end_time = float(key_info.get("end_time", 0.0))
        pts_time = float(key_info.get("pts_time", 0.0))
        fps = float(key_info.get("fps", 0.0))

        # Tags: merge OD_tags and RAM_tags
        tags = list(set(record.get("OD_tags", []) + record.get("RAM_tags", [])))
        tags = tags[:TAGS_MAX_COUNT]
        tags = [t[:TAG_ITEM_MAX_LEN] for t in tags]

        # YouTube URL
        youtube_url = youtube_map.get(video_path, "")

        # Milvus buffer (16 fields)
        milvus_buffer[0].append(video_id)       # video_id
        milvus_buffer[1].append(video_path)     # video_path
        milvus_buffer[2].append(youtube_url)    # youtube_url
        milvus_buffer[3].append(frame_id)       # frame_index
        milvus_buffer[4].append(frame_idx)      # frame_idx
        milvus_buffer[5].append(frame_path)     # frame_path
        milvus_buffer[6].append(shot_idx)       # shot_idx
        milvus_buffer[7].append(start_time)     # start_time
        milvus_buffer[8].append(end_time)       # end_time
        milvus_buffer[9].append(pts_time)       # pts_time
        milvus_buffer[10].append(fps)           # fps
        milvus_buffer[11].append(pts_time)      # timestamp
        milvus_buffer[12].append(tags)          # tags
        milvus_buffer[13].append(embedding.tolist())  # embedding

        # ES buffer (ocr_text / asr_text from ocr_text / audio_text)
        es_doc = frame_doc_from_record(record)
        if es_doc is not None:
            es_buffer.append(es_doc)

        # Flush Milvus
        if len(milvus_buffer[0]) >= MILVUS_BATCH:
            col.insert(milvus_buffer)
            total_frames += len(milvus_buffer[0])
            milvus_buffer = [[] for _ in range(14)]

        # Flush ES
        if len(es_buffer) >= ES_BATCH:
            bulk_insert_es(es, es_buffer)
            es_buffer = []

        processed.add(file_path)
        count += 1
        if count % 1000 == 0:
            elapsed = time.time() - t0
            fps_rate = total_frames / elapsed if elapsed > 0 else 0
            print(f"  [{count}] {total_frames} frames | {fps_rate:.1f} frames/s")

    # Final flush
    if milvus_buffer[0]:
        col.insert(milvus_buffer)
        total_frames += len(milvus_buffer[0])
    if es_buffer:
        bulk_insert_es(es, es_buffer)

    elapsed = time.time() - t0
    print(f"  Done: {count} records, {total_frames} frames in {elapsed:.1f}s")
    return count, total_frames


# ── Main ────────────────────────────────────────────────────────────────────
def load(
    batch: int | None = None,
    all_batches: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
) -> None:
    connect_milvus()
    col = ensure_milvus_collection()

    es = connect_elasticsearch()
    ensure_es_index(es)

    youtube_map = load_youtube_urls()

    processed: set[str] = set()
    total_videos = 0
    total_frames = 0

    t0 = time.time()

    if all_batches or batch is None:
        dirs = [BATCH1_DIR, BATCH2_DIR]
    elif batch == 1:
        dirs = [BATCH1_DIR]
    elif batch == 2:
        dirs = [BATCH2_DIR]
    else:
        print(f"Invalid batch: {batch}")
        return

    for batch_dir in dirs:
        videos, frames = load_batch(
            batch_dir, youtube_map, es, col, processed, limit, dry_run
        )
        total_videos += videos
        total_frames += frames

    col.flush()
    save_checkpoint(processed)

    elapsed = time.time() - t0
    print(f"\nDone! {total_frames} frames loaded in {elapsed:.1f}s")
    print(f"  Videos: {total_videos} processed")
    print(f"  Milvus: {COLLECTION_NAME} ({col.num_entities} entities)")
    print(f"  ES: video_texts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load pre-computed embeddings into Milvus + ES")
    parser.add_argument("--batch", type=int, choices=[1, 2], help="Load specific batch (1 or 2)")
    parser.add_argument("--all", action="store_true", help="Load both batches")
    parser.add_argument("--limit", type=int, help="Max records to process")
    parser.add_argument("--dry-run", action="store_true", help="Skip actual insert (for testing)")
    args = parser.parse_args()

    load(
        batch=args.batch,
        all_batches=args.all,
        limit=args.limit,
        dry_run=args.dry_run,
    )
