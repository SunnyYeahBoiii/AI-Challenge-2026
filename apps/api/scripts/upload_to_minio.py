"""
Upload local keyframes + video files to MinIO, mirroring the key layout that
app/services/storage.py builds public URLs from:

    keyframes bucket: {level}/{video_id}/{frame_index}.webp   (level = video_id[:3])
    videos bucket:     {video_id}.mp4

Buckets are created (if missing) with a public-read policy, since storage.py
returns plain path-style URLs rather than presigned ones.

Usage:
    cd apps/api
    uv run python scripts/upload_to_minio.py --keyframes
    uv run python scripts/upload_to_minio.py --videos /Volumes/external/AIC_videos
    uv run python scripts/upload_to_minio.py --keyframes --videos /Volumes/external/AIC_videos
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_SECURE = os.getenv("MINIO_SECURE", "true").lower() == "true"
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET_KEYFRAMES = os.getenv("MINIO_BUCKET_KEYFRAMES", "keyframes")
MINIO_BUCKET_VIDEOS = os.getenv("MINIO_BUCKET_VIDEOS", "videos")

KEYFRAMES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "keyframes" / "keyframes"


def _client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def _public_read_policy(bucket: str) -> str:
    return json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{bucket}/*"],
        }],
    })


def _ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        print(f"Created bucket '{bucket}'")
    client.set_bucket_policy(bucket, _public_read_policy(bucket))


def upload_keyframes(client: Minio) -> int:
    bucket = MINIO_BUCKET_KEYFRAMES
    _ensure_bucket(client, bucket)
    count = 0
    for path in KEYFRAMES_DIR.glob("*/*/*.webp"):
        level, video_id, filename = path.parts[-3:]
        key = f"{level}/{video_id}/{filename}"
        client.fput_object(bucket, key, str(path), content_type="image/webp")
        count += 1
        if count % 2000 == 0:
            print(f"  [{count}] keyframes uploaded")
    return count


def _video_id_from_path(path: Path) -> str:
    # AIC-style naming (e.g. L21_V001.mp4) uses the filename stem directly as
    # video_id. Adjust here if the external drive's layout differs.
    return path.stem


def upload_videos(client: Minio, videos_dir: Path) -> int:
    bucket = MINIO_BUCKET_VIDEOS
    _ensure_bucket(client, bucket)
    count = 0
    for path in videos_dir.rglob("*.mp4"):
        video_id = _video_id_from_path(path)
        key = f"{video_id}.mp4"
        client.fput_object(bucket, key, str(path), content_type="video/mp4")
        count += 1
        print(f"  [{count}] {key}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload keyframes/videos to MinIO")
    parser.add_argument("--keyframes", action="store_true", help=f"Upload {KEYFRAMES_DIR}")
    parser.add_argument("--videos", type=Path, help="Directory of source .mp4 files to upload")
    args = parser.parse_args()

    if not args.keyframes and not args.videos:
        raise SystemExit("Nothing to do: pass --keyframes and/or --videos <dir>")

    client = _client()

    try:
        if args.keyframes:
            n = upload_keyframes(client)
            print(f"Done: {n} keyframes -> bucket '{MINIO_BUCKET_KEYFRAMES}'")
        if args.videos:
            if not args.videos.is_dir():
                raise SystemExit(f"Not a directory: {args.videos}")
            n = upload_videos(client, args.videos)
            print(f"Done: {n} videos -> bucket '{MINIO_BUCKET_VIDEOS}'")
    except S3Error as e:
        raise SystemExit(f"MinIO error: {e}")


if __name__ == "__main__":
    main()
