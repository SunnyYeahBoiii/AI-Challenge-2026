"""
One-shot cleanup: delete the old flat {level}/{video_id}.mp4 objects from the
MinIO 'videos' bucket ahead of the HLS migration (see hls_migrate.py).

Only deletes keys matching the flat pattern (exactly one '/', ending in
.mp4) — HLS assets live under {level}/{video_id}/... (two or more '/'),
so a rerun after migration starts is a no-op rather than eating new data.

Usage:
    cd apps/api
    uv run python scripts/delete_old_mp4s.py --dry-run
    uv run python scripts/delete_old_mp4s.py
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio
from minio.deleteobjects import DeleteObject
from minio.error import S3Error

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_SECURE = os.getenv("MINIO_SECURE", "true").lower() == "true"
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET_VIDEOS = os.getenv("MINIO_BUCKET_VIDEOS", "videos")

_FLAT_MP4 = re.compile(r"^[^/]+/[^/]+\.mp4$")


def _client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete flat legacy mp4 objects")
    parser.add_argument("--dry-run", action="store_true", help="List only, delete nothing")
    args = parser.parse_args()

    client = _client()
    keys = [
        obj.object_name
        for obj in client.list_objects(MINIO_BUCKET_VIDEOS, recursive=True)
        if obj.object_name and _FLAT_MP4.match(obj.object_name)
    ]

    print(f"Found {len(keys)} flat mp4 object(s) in bucket '{MINIO_BUCKET_VIDEOS}'")
    if not keys:
        return
    if args.dry_run:
        for k in keys[:20]:
            print(f"  would delete {k}")
        if len(keys) > 20:
            print(f"  ... and {len(keys) - 20} more")
        return

    errors = list(
        client.remove_objects(
            MINIO_BUCKET_VIDEOS, (DeleteObject(k) for k in keys)
        )
    )
    ok = len(keys) - len(errors)
    print(f"Deleted {ok}/{len(keys)}")
    for e in errors:
        print(f"  FAIL {e.object_name}: {e}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except S3Error as e:
        raise SystemExit(f"MinIO error: {e}") from e
