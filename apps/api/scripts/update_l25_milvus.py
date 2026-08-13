"""Remove old L25 frames from every Milvus collection and re-insert the
updated L25 subset from the regenerated embedding zips + the updated
concatenate-data-b1.json (tags source).

Usage:
    cd apps/api
    uv run python scripts/update_l25_milvus.py
"""

import json
import os
import sys
import time
import warnings
import zipfile
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from pymilvus import Collection, connections

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")

DOWNLOAD_DIR = Path("/Users/sunny/Downloads/updated_L25")
VIDEO_PREFIX = "L25"
BATCH = 8000
EXPECTED_L25 = 18790

# zip -> collection, dim.
ZIP_COLLECTIONS = [
    ("bge-vl-large.zip", "data_frames", 768),
    ("metaclip2-worldwide-huge.zip", "df_meta", 1024),
    ("beit3-large-coco-retrieval-384.zip", "df_beit", 1024),
]


def load_l25_tags() -> dict[str, list[str]]:
    """frame_uid -> tags from the updated json (zip L25 records carry none)."""
    with open(DOWNLOAD_DIR / "concatenate-data-b1.json", encoding="utf-8") as f:
        data = json.load(f)
    tags: dict[str, list[str]] = {}
    for rec in data:
        video_id = str(rec.get("video_path", "")).rstrip("/").split("/")[-1]
        if not video_id.startswith(VIDEO_PREFIX):
            continue
        frame_idx = str(rec["keyframe_info"]["frame_idx"]).zfill(8)
        merged = list(set(rec.get("OD_tags", []) + rec.get("RAM_tags", [])))[:100]
        tags[f"{video_id}:{frame_idx}"] = [t[:32] for t in merged]
    return tags


def insert_l25_from_zip(zip_path: Path, col: Collection, tags: dict[str, list[str]]) -> int:
    with zipfile.ZipFile(zip_path) as zf:
        names = sorted(zf.namelist())
        rec_names = [n for n in names if n.endswith(".jsonl")]
        emb_names = [n for n in names if n.endswith(".npy")]
        if len(rec_names) != len(emb_names):
            raise SystemExit(f"Shard mismatch in {zip_path.name}: {len(rec_names)} vs {len(emb_names)}")

        buffer: list[list[object]] = [[] for _ in range(14)]
        count = 0
        for rec_name, emb_name in zip(rec_names, emb_names):
            records = [json.loads(line) for line in zf.read(rec_name).decode().splitlines()]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                embeddings = np.load(zf.open(emb_name), allow_pickle=False)
            if len(records) != len(embeddings):
                raise SystemExit(f"Row mismatch in {rec_name}")
            for rec, emb in zip(records, embeddings):
                if not rec["video_id"].startswith(VIDEO_PREFIX):
                    continue
                frame_idx = int(rec["frame_idx"])
                buffer[0].append(rec["video_id"])
                buffer[1].append(str(rec["video_path"]).rstrip("/"))
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
                buffer[12].append(tags.get(rec["frame_uid"], list(rec.get("tags") or [])))
                buffer[13].append(emb.astype(np.float32).tolist())
                count += 1
                if len(buffer[0]) >= BATCH:
                    col.insert(buffer)
                    buffer = [[] for _ in range(14)]
        if buffer[0]:
            col.insert(buffer)
    return count


def main() -> None:
    connections.connect(alias="default", uri=MILVUS_URI, token=MILVUS_TOKEN)
    tags = load_l25_tags()
    print(f"L25 tag entries from json: {len(tags)}")
    if len(tags) != EXPECTED_L25:
        raise SystemExit(f"Unexpected L25 json count: {len(tags)}")

    for zip_name, coll_name, dim in ZIP_COLLECTIONS:
        col = Collection(coll_name)
        col.load()
        before = col.num_entities
        t0 = time.time()

        col.delete(f'video_id like "{VIDEO_PREFIX}%"')
        col.flush()
        after_delete = col.num_entities
        print(f"[{coll_name}] deleted {before - after_delete} in {time.time() - t0:.1f}s")

        n = insert_l25_from_zip(DOWNLOAD_DIR / zip_name, col, tags)
        if n != EXPECTED_L25:
            raise SystemExit(f"[{coll_name}] inserted {n} != expected {EXPECTED_L25}")
        col.flush()
        print(f"[{coll_name}] inserted {n}; final entities {col.num_entities} (expected 134770)")


if __name__ == "__main__":
    main()
