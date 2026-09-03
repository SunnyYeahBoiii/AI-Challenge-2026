"""
Load a self-contained embedding artifact zip (embeddings-*.npy + records-*.jsonl
+ manifest.json, index-aligned) into a fresh Milvus collection.

Usage:
    cd apps/api
    uv run python scripts/load_zip_embeddings.py \
        --zip /path/to/metaclip2-worldwide-huge.zip --collection df_meta
    uv run python scripts/load_zip_embeddings.py \
        --zip /path/to/beit3-large-coco-retrieval-384.zip --collection df_beit --drop
"""

import argparse
import io
import json
import os
import time
import zipfile
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")

MILVUS_BATCH = 8000
TAG_ITEM_MAX_LEN = 32
TAGS_MAX_COUNT = 100


def connect_milvus() -> None:
    connections.connect(alias="default", uri=MILVUS_URI, token=MILVUS_TOKEN)


def ensure_collection(name: str, dim: int, drop: bool = False) -> Collection:
    if utility.has_collection(name):
        if drop:
            utility.drop_collection(name)
        else:
            raise SystemExit(
                f"Collection '{name}' already exists — rerun with --drop to replace it"
            )

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
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    col = Collection(name, CollectionSchema(fields, description="Video frames"))
    col.create_index("embedding", {"metric_type": "IP", "index_type": "AUTOINDEX", "params": {}})
    print(f"Created collection '{name}' (dim={dim}) with AUTOINDEX.")
    return col


def load_zip(zip_path: Path, col: Collection) -> int:
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        manifest_name = next(n for n in names if n.endswith("manifest.json"))
        manifest = json.loads(zf.read(manifest_name))
        total = int(manifest["total_frames"])
        model_id = manifest.get("model", {}).get("id", "unknown")
        print(f"Manifest: {model_id}, {total} frames")

        shard_names = sorted(
            n
            for n in names
            if n.endswith(".jsonl") and "records-" in n and not n.endswith("manifest.json")
        )
        emb_names = sorted(n for n in names if n.endswith(".npy"))
        if len(shard_names) != len(emb_names):
            raise SystemExit(f"Shard mismatch: {len(shard_names)} records vs {len(emb_names)} npy")

        buffer: list[list[object]] = [[] for _ in range(14)]
        count = 0
        t0 = time.time()
        for rec_name, emb_name in zip(shard_names, emb_names):
            records = [json.loads(line) for line in zf.read(rec_name).decode().splitlines()]
            with io.BytesIO(zf.read(emb_name)) as f:
                embeddings = np.load(f, allow_pickle=False)
            if len(records) != len(embeddings):
                raise SystemExit(f"Row mismatch in {rec_name}: {len(records)} vs {len(embeddings)}")

            for rec, emb in zip(records, embeddings):
                tags = list(rec.get("tags") or [])[:TAGS_MAX_COUNT]
                tags = [t[:TAG_ITEM_MAX_LEN] for t in tags]
                frame_idx = int(rec.get("frame_idx") or rec.get("frame_index") or 0)
                buffer[0].append(rec.get("video_id", ""))
                buffer[1].append(str(rec.get("video_path", "")).rstrip("/"))
                buffer[2].append(rec.get("youtube_url", ""))
                buffer[3].append(frame_idx)
                buffer[4].append(frame_idx)
                buffer[5].append(rec.get("frame_path", ""))
                buffer[6].append(int(rec.get("shot_idx") or 0))
                buffer[7].append(float(rec.get("start_time") or 0.0))
                buffer[8].append(float(rec.get("end_time") or 0.0))
                buffer[9].append(float(rec.get("pts_time") or 0.0))
                buffer[10].append(float(rec.get("fps") or 0.0))
                buffer[11].append(float(rec.get("timestamp") or rec.get("pts_time") or 0.0))
                buffer[12].append(tags)
                buffer[13].append(emb.astype(np.float32).tolist())
                count += 1
                if len(buffer[0]) >= MILVUS_BATCH:
                    col.insert(buffer)
                    buffer = [[] for _ in range(14)]
            if count % 20000 == 0:
                elapsed = time.time() - t0
                print(f"  [{count}/{total}] {count / elapsed if elapsed else 0:.0f} rows/s")

        if buffer[0]:
            col.insert(buffer)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Load an embedding zip into Milvus")
    parser.add_argument("--zip", required=True, help="Path to the artifact zip")
    parser.add_argument("--collection", required=True, help="Target collection name")
    parser.add_argument("--drop", action="store_true", help="Drop the collection if it exists")
    args = parser.parse_args()

    zip_path = Path(args.zip)
    if not zip_path.exists():
        raise SystemExit(f"Zip not found: {zip_path}")

    connect_milvus()
    col = ensure_collection(args.collection, dim=1024, drop=args.drop)
    t0 = time.time()
    count = load_zip(zip_path, col)
    col.flush()
    print(f"\nDone: {count} frames into '{args.collection}' in {time.time() - t0:.1f}s")
    print(f"  Entities: {col.num_entities}")


if __name__ == "__main__":
    main()
