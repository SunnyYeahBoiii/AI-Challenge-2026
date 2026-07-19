"""
Load keyframe images + video metadata into Milvus and Elasticsearch.

Usage:
    cd apps/api
    uv run python scripts/load_data.py

Expects .env in apps/api/ with MILVUS_URI, ES_URL, etc.
"""

import csv
import json
import os
import time
from pathlib import Path

import numpy as np
import open_clip
import torch
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from PIL import Image
from pymilvus import (
    Collection,
    DataType,
    FieldSchema,
    CollectionSchema,
    connections,
    utility,
)

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_USER = os.getenv("ES_USER", "")
ES_PASS = os.getenv("ES_PASS", "")

DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data"
KEYFRAMES_DIR = DATA_ROOT / "keyframes" / "keyframes"
MAP_DIR = DATA_ROOT / "map_keyframes" / "map_keyframes"
MEDIA_DIR = DATA_ROOT / "media-info-aic25-b1" / "media-info"

EMBEDDING_DIM = 1024
BATCH_SIZE = 64  # images per CLIP batch
MILVUS_BATCH = 500  # rows per Milvus insert
ES_BATCH = 200  # docs per ES bulk

COLLECTION_NAME = "keyframes"
ES_INDEX = "videos"

LEVELS = ["L21", "L22", "L23", "L24"]

# ── CLIP model ──────────────────────────────────────────────────────────────
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading CLIP model on {device}...")
model, _, preprocess = open_clip.create_model_and_transforms(
    "ViT-H-14", pretrained="dfn5b"
)
tokenizer = open_clip.get_tokenizer("ViT-H-14")
model = model.to(device).eval()
print("CLIP model loaded.")


# ── Milvus ──────────────────────────────────────────────────────────────────
def connect_milvus():
    print(f"Connecting to Milvus at {MILVUS_URI}...")
    connections.connect(alias="default", uri=MILVUS_URI)
    print("Milvus connected.")


def ensure_milvus_collection() -> Collection:
    if utility.has_collection(COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' exists.")
        return Collection(COLLECTION_NAME)

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="video_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="frame_index", dtype=DataType.INT64),
        FieldSchema(name="shot_idx", dtype=DataType.INT64),
        FieldSchema(name="start_time", dtype=DataType.FLOAT),
        FieldSchema(name="end_time", dtype=DataType.FLOAT),
        FieldSchema(name="pts_time", dtype=DataType.FLOAT),
        FieldSchema(name="fps", dtype=DataType.FLOAT),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
    ]
    schema = CollectionSchema(fields, description="Video keyframe embeddings")
    col = Collection(COLLECTION_NAME, schema)
    print(f"Created collection '{COLLECTION_NAME}'.")
    return col


# ── Elasticsearch ───────────────────────────────────────────────────────────
def connect_elasticsearch() -> Elasticsearch:
    print(f"Connecting to Elasticsearch at {ES_URL}...")
    if ES_USER and ES_PASS:
        es = Elasticsearch(ES_URL, basic_auth=(ES_USER, ES_PASS))
    else:
        es = Elasticsearch(ES_URL)
    if not es.ping():
        raise ConnectionError("Cannot ping Elasticsearch")
    print("Elasticsearch connected.")
    return es


def ensure_es_index(es: Elasticsearch):
    if es.indices.exists(index=ES_INDEX):
        print(f"Index '{ES_INDEX}' exists.")
        return

    mapping = {
        "mappings": {
            "properties": {
                "video_id": {"type": "keyword"},
                "title": {"type": "text"},
                "description": {"type": "text"},
                "keywords": {"type": "keyword"},
                "author": {"type": "keyword"},
                "channel_id": {"type": "keyword"},
                "length": {"type": "integer"},
                "publish_date": {"type": "keyword"},
                "thumbnail_url": {"type": "keyword"},
                "watch_url": {"type": "keyword"},
                "level": {"type": "keyword"},
                "frame_count": {"type": "integer"},
            }
        }
    }
    es.indices.create(index=ES_INDEX, body=mapping)
    print(f"Created index '{ES_INDEX}'.")


# ── Data scanning ───────────────────────────────────────────────────────────
def scan_videos():
    """Yield (video_id, level, keyframe_dir, csv_path, media_info_path)."""
    for level in LEVELS:
        kf_level = KEYFRAMES_DIR / level
        map_level = MAP_DIR / level
        if not kf_level.exists():
            continue
        for video_dir in sorted(kf_level.iterdir()):
            if not video_dir.is_dir():
                continue
            video_id = video_dir.name  # e.g. L21_V001
            csv_path = map_level / f"{video_id}.csv"
            media_path = MEDIA_DIR / f"{video_id}.json"
            yield video_id, level, video_dir, csv_path, media_path


def read_csv(csv_path: Path) -> list[dict]:
    """Read keyframe mapping CSV."""
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "n": int(row["n"]),
                    "shot_idx": int(row["shot_idx"]),
                    "start_time": float(row["start_time"]),
                    "end_time": float(row["end_time"]),
                    "pts_time": float(row["pts_time"]),
                    "fps": float(row["fps"]),
                    "frame_idx": int(row["frame_idx"]),
                }
            )
    return rows


def read_media_info(json_path: Path) -> dict | None:
    if not json_path.exists():
        return None
    with open(json_path) as f:
        return json.load(f)


# ── Embedding ───────────────────────────────────────────────────────────────
def embed_images(image_paths: list[Path]) -> np.ndarray:
    """Embed a batch of images with CLIP. Returns (N, 1024) array."""
    images = []
    for p in image_paths:
        img = Image.open(p).convert("RGB")
        images.append(preprocess(img))

    batch = torch.stack(images).to(device)
    with torch.no_grad():
        features = model.encode_image(batch)
        features = features / features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy().astype(np.float32)


# ── Main load ───────────────────────────────────────────────────────────────
def load():
    connect_milvus()
    col = ensure_milvus_collection()

    es = connect_elasticsearch()
    ensure_es_index(es)

    videos = list(scan_videos())
    print(f"\nFound {len(videos)} videos to process.\n")

    total_frames = 0
    milvus_buffer: list[list] = []  # [video_id, frame_index, shot_idx, start, end, pts, fps, embedding]
    es_buffer: list[dict] = []

    t0 = time.time()

    for vi, (video_id, level, kf_dir, csv_path, media_path) in enumerate(videos):
        csv_rows = read_csv(csv_path) if csv_path.exists() else []
        media_info = read_media_info(media_path)

        # Index video metadata into ES
        if media_info:
            doc = {
                "video_id": video_id,
                "level": level,
                "title": media_info.get("title", ""),
                "description": media_info.get("description", ""),
                "keywords": media_info.get("keywords", []),
                "author": media_info.get("author", ""),
                "channel_id": media_info.get("channel_id", ""),
                "length": media_info.get("length", 0),
                "publish_date": media_info.get("publish_date", ""),
                "thumbnail_url": media_info.get("thumbnail_url", ""),
                "watch_url": media_info.get("watch_url", ""),
                "frame_count": len(csv_rows),
            }
            es_buffer.append(doc)

        # Collect image paths for this video
        image_paths = sorted(kf_dir.glob("*.webp"))

        # Build CSV lookup: n -> row info
        csv_lookup = {row["n"]: row for row in csv_rows}

        # Embed in batches
        for bi in range(0, len(image_paths), BATCH_SIZE):
            batch_paths = image_paths[bi : bi + BATCH_SIZE]
            embeddings = embed_images(batch_paths)

            for j, img_path in enumerate(batch_paths):
                # Extract frame number from filename (0001.webp -> 1)
                frame_num = int(img_path.stem)
                row_info = csv_lookup.get(frame_num, {})

                milvus_buffer.append(
                    [
                        video_id,
                        frame_num,
                        row_info.get("shot_idx", 0),
                        row_info.get("start_time", 0.0),
                        row_info.get("end_time", 0.0),
                        row_info.get("pts_time", 0.0),
                        row_info.get("fps", 0.0),
                        embeddings[j].tolist(),
                    ]
                )

            # Flush Milvus buffer
            if len(milvus_buffer) >= MILVUS_BATCH:
                col.insert(milvus_buffer)
                total_frames += len(milvus_buffer)
                milvus_buffer = []

        # Flush ES buffer
        if len(es_buffer) >= ES_BATCH:
            _bulk_insert_es(es, es_buffer)
            es_buffer = []

        elapsed = time.time() - t0
        fps_rate = total_frames / elapsed if elapsed > 0 else 0
        print(
            f"[{vi+1}/{len(videos)}] {video_id}: {len(image_paths)} frames "
            f"| {total_frames} total frames embedded | {fps_rate:.1f} frames/s"
        )

    # Final flush
    if milvus_buffer:
        col.insert(milvus_buffer)
        total_frames += len(milvus_buffer)
    if es_buffer:
        _bulk_insert_es(es, es_buffer)

    col.flush()
    col.load()

    elapsed = time.time() - t0
    print(f"\nDone! {total_frames} frames loaded in {elapsed:.1f}s")
    print(f"  Milvus collection: {COLLECTION_NAME} ({col.num_entities} entities)")
    print(f"  ES index: {ES_INDEX}")


def _bulk_insert_es(es: Elasticsearch, docs: list[dict]):
    """Bulk insert documents into Elasticsearch."""
    body = []
    for doc in docs:
        body.append({"index": {"_index": ES_INDEX}})
        body.append(doc)
    es.bulk(body=body, refresh="wait_for")


if __name__ == "__main__":
    load()
