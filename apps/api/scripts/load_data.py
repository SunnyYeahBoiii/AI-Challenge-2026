"""
Load AIC2026 batch b1 (videos L21-L30) pre-computed BGE-VL embeddings +
metadata into Milvus and Elasticsearch. The embeddings are BGE-VL-large
vectors, so this loads into BgeVlEncoder.collection_name — the collection the
BGE-VL-large encoder searches at query time. Loading data for the other
encoders (MetaCLIP, BEiT-3) is out of scope: it requires re-encoding every
keyframe with each model, which this script does not do.

Usage:
    cd apps/api
    uv run python scripts/load_data.py
    uv run python scripts/load_data.py --limit 10 --dry-run

Expects .env in apps/api/ with MILVUS_URI, ES_URL, etc.
Data files (index-aligned, chunk k holds rows k*1000..k*1000+999):
    - data/Data/Batch1/concatenate-data.json        (OCR/ASR + tags per frame)
    - data/Data/Batch1/embeddings/embeddings-*.npy  (768-dim BGE-VL vectors)
    - data/Data/Batch1/records/records-*.jsonl      (frame_uid + youtube_url)
"""

import argparse
import glob
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
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from es_common import (  # noqa: E402
    ES_BATCH,
    bulk_insert_es,
    connect_elasticsearch,
    ensure_es_index,
    frame_doc_from_record,
)
from app.services.encoders.bge_vl import BgeVlEncoder  # noqa: E402

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")

DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data"
BATCH1_DIR = DATA_ROOT / "Data" / "Batch1"

# This dataset holds precomputed BGE-VL embeddings — load it into the same
# collection app.services.encoders.bge_vl.BgeVlEncoder searches at query time.
EMBEDDING_DIM = BgeVlEncoder.embedding_dim
CHUNK_SIZE = 1000
MILVUS_BATCH = 8000

COLLECTION_NAME = BgeVlEncoder.collection_name

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
    es: Elasticsearch,
    col: Collection,
    processed: set[str],
    limit: int | None = None,
    dry_run: bool = False,
) -> int:
    json_path = BATCH1_DIR / "concatenate-data.json"
    npy_files = sorted(glob.glob(str(BATCH1_DIR / "embeddings" / "embeddings-*.npy")))
    jsonl_files = sorted(glob.glob(str(BATCH1_DIR / "records" / "records-*.jsonl")))

    if not json_path.exists():
        raise FileNotFoundError(json_path)
    if not npy_files or not jsonl_files:
        raise FileNotFoundError("Missing embeddings/ or records/ chunks")

    with open(json_path, encoding="utf-8") as f:
        json_data = json.load(f)
    n_rows = sum(np.load(f, mmap_mode="r").shape[0] for f in npy_files)
    print(f"JSON records: {len(json_data)}, embedding rows: {n_rows}, chunks: {len(npy_files)}")
    if len(json_data) != n_rows:
        raise ValueError("JSON/embedding count mismatch — aborting")

    youtube_urls: dict[str, str] = {}
    for jsonl_file in jsonl_files:
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                youtube_urls[rec["frame_uid"]] = rec.get("youtube_url", "")
    print(f"Loaded {len(youtube_urls)} youtube_url mappings.")

    milvus_buffer: list[list[object]] = [[] for _ in range(14)]
    es_buffer: list[dict[str, object]] = []
    t0 = time.time()
    count = 0
    total_frames = 0
    chunk_embeddings: np.ndarray | None = None

    for i, record in enumerate(json_data):
        if limit and count >= limit:
            break

        file_path = record.get("file_path", "")
        if file_path in processed:
            continue

        key_info = record.get("keyframe_info", {})
        video_id = str(record.get("video_path", "")).rstrip("/").split("/")[-1]
        frame_idx = int(key_info.get("frame_idx", 0))
        frame_uid = f"{video_id}:{frame_idx:08d}"

        chunk_idx = i // CHUNK_SIZE
        row_idx = i % CHUNK_SIZE
        if chunk_embeddings is None or chunk_idx != (i - 1) // CHUNK_SIZE:
            chunk_embeddings = np.load(npy_files[chunk_idx])
            if len(chunk_embeddings) != CHUNK_SIZE and chunk_idx != len(npy_files) - 1:
                raise ValueError(f"Unexpected chunk size in {npy_files[chunk_idx]}")
            print(f"  Loaded chunk {chunk_idx}: {npy_files[chunk_idx]}")

        shot_idx = int(key_info.get("shot_idx") or 0)
        start_time = float(key_info.get("start_time") or 0.0)
        end_time = float(key_info.get("end_time") or 0.0)
        pts_time = float(key_info.get("timestamp") or key_info.get("pts_time") or 0.0)
        fps = float(key_info.get("fps") or 0.0)

        tags = list(set(record.get("OD_tags", []) + record.get("RAM_tags", [])))[:TAGS_MAX_COUNT]
        tags = [t[:TAG_ITEM_MAX_LEN] for t in tags]

        milvus_buffer[0].append(video_id)
        milvus_buffer[1].append(str(record.get("video_path", "")).rstrip("/"))
        milvus_buffer[2].append(youtube_urls.get(frame_uid, ""))
        milvus_buffer[3].append(frame_idx)
        milvus_buffer[4].append(frame_idx)
        milvus_buffer[5].append(file_path)
        milvus_buffer[6].append(shot_idx)
        milvus_buffer[7].append(start_time)
        milvus_buffer[8].append(end_time)
        milvus_buffer[9].append(pts_time)
        milvus_buffer[10].append(fps)
        milvus_buffer[11].append(pts_time)
        milvus_buffer[12].append(tags)
        milvus_buffer[13].append(chunk_embeddings[row_idx].tolist())

        es_doc = frame_doc_from_record(record)
        if es_doc is not None:
            es_buffer.append(es_doc)

        if not dry_run:
            if len(milvus_buffer[0]) >= MILVUS_BATCH:
                col.insert(milvus_buffer)
                total_frames += len(milvus_buffer[0])
                milvus_buffer = [[] for _ in range(14)]
            if len(es_buffer) >= ES_BATCH:
                bulk_insert_es(es, es_buffer)
                es_buffer = []

        processed.add(file_path)
        count += 1
        if count % 5000 == 0:
            elapsed = time.time() - t0
            rate = count / elapsed if elapsed > 0 else 0
            print(f"  [{count}] {rate:.0f} records/s")

    if not dry_run:
        if milvus_buffer[0]:
            col.insert(milvus_buffer)
            total_frames += len(milvus_buffer[0])
        if es_buffer:
            bulk_insert_es(es, es_buffer)

    elapsed = time.time() - t0
    print(f"  Done: {count} records ({total_frames} inserted) in {elapsed:.1f}s")
    return count


# ── Main ────────────────────────────────────────────────────────────────────
def load(limit: int | None = None, dry_run: bool = False) -> None:
    connect_milvus()
    col = ensure_milvus_collection()
    es = connect_elasticsearch()
    ensure_es_index(es)

    processed = load_checkpoint() if not dry_run else set()
    t0 = time.time()
    load_batch(es, col, processed, limit, dry_run)

    if not dry_run:
        col.flush()
        save_checkpoint(processed)
        elapsed = time.time() - t0
        print(f"\nDone in {elapsed:.1f}s")
        print(f"  Milvus: {COLLECTION_NAME} ({col.num_entities} entities)")
        print("  ES: video_texts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load AIC2026 b1 embeddings into Milvus + ES")
    parser.add_argument("--limit", type=int, help="Max records to process")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; skip DB writes")
    args = parser.parse_args()

    load(limit=args.limit, dry_run=args.dry_run)
