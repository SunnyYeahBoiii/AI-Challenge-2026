"""
Batch-convert local source MP4s to HLS (fMP4/CMAF, -c copy) and upload to the
MinIO 'videos' bucket under {level}/{video_id}/{index.m3u8,init.mp4,segment*.m4s}.

Meant to run after delete_old_mp4s.py has cleared the old flat
{level}/{video_id}.mp4 keys — see docs/adr for why. Resumable: a video is
skipped if its index.m3u8 already exists in the bucket, so a killed/rerun
job just picks up where it left off.

Requires: ffmpeg on PATH, MinIO credentials in apps/api/.env

Usage:
    cd apps/api
    uv run python scripts/hls_migrate.py --videos-dir ../../data/videos_grouped --jobs 6
    uv run python scripts/hls_migrate.py --videos-dir ../../data/videos_grouped --video-id L26_V094 --force
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_SECURE = os.getenv("MINIO_SECURE", "true").lower() == "true"
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET_VIDEOS = os.getenv("MINIO_BUCKET_VIDEOS", "videos")

HLS_SEGMENT_SECONDS = 6
_CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".mp4": "video/mp4",
    ".m4s": "video/iso.segment",
}
# HLS assets are content-addressed by video_id and never change once written.
_CACHE_CONTROL = "public, max-age=31536000, immutable"

_print_lock = threading.Lock()


def _client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg not found. Install with `brew install ffmpeg`.")
    return ffmpeg


def _video_id_from_path(path: Path) -> str:
    return path.stem


def _already_migrated(client: Minio, prefix: str) -> bool:
    try:
        client.stat_object(MINIO_BUCKET_VIDEOS, f"{prefix}/index.m3u8")
        return True
    except S3Error:
        return False


def segment_to_hls(src: Path, out_dir: Path, ffmpeg: str) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(src),
            "-c",
            "copy",
            "-f",
            "hls",
            "-hls_time",
            str(HLS_SEGMENT_SECONDS),
            "-hls_playlist_type",
            "vod",
            "-hls_segment_type",
            "fmp4",
            "-hls_fmp4_init_filename",
            "init.mp4",
            "-hls_segment_filename",
            str(out_dir / "segment%03d.m4s"),
            str(out_dir / "index.m3u8"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _put_with_retry(client: Minio, key: str, file_path: Path, *, attempts: int = 4) -> None:
    last: BaseException | None = None
    for i in range(attempts):
        try:
            client.fput_object(
                MINIO_BUCKET_VIDEOS,
                key,
                str(file_path),
                content_type=_CONTENT_TYPES.get(file_path.suffix, "application/octet-stream"),
                metadata={"Cache-Control": _CACHE_CONTROL},
            )
            return
        except Exception as exc:  # noqa: BLE001 — network/CDN errors vary by type
            last = exc
            wait = 2**i
            with _print_lock:
                print(f"    retry {i + 1}/{attempts} {key}: {exc} (sleep {wait}s)", flush=True)
            time.sleep(wait)
    assert last is not None
    raise last


def process_video(path: Path, ffmpeg: str, *, force: bool, index: int, total: int) -> str:
    video_id = _video_id_from_path(path)
    level = video_id[:3]
    prefix = f"{level}/{video_id}"
    client = _client()  # one client per task — safer across threads

    if not force and _already_migrated(client, prefix):
        return f"  [{index}/{total}] skip {prefix} (already migrated)"

    with tempfile.TemporaryDirectory(prefix="hls_migrate_") as tmp:
        out_dir = Path(tmp)
        segment_to_hls(path, out_dir, ffmpeg)
        files = sorted(out_dir.iterdir())
        # index.m3u8 uploaded last: its presence is the resume/completion marker.
        files.sort(key=lambda f: f.name == "index.m3u8")
        for f in files:
            _put_with_retry(client, f"{prefix}/{f.name}", f)

    msg = f"  [{index}/{total}] ok {prefix} ({len(files)} objects)"
    with _print_lock:
        print(msg, flush=True)
    return msg


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate local MP4s to HLS on MinIO")
    parser.add_argument("--videos-dir", type=Path, required=True, help="Local source video dir")
    parser.add_argument("--video-id", help="Process a single video id, e.g. L26_V094")
    parser.add_argument("--jobs", type=int, default=4, help="Parallel ffmpeg+upload workers")
    parser.add_argument("--force", action="store_true", help="Reprocess even if already migrated")
    args = parser.parse_args()

    if not args.videos_dir.is_dir():
        raise SystemExit(f"Not a directory: {args.videos_dir}")

    ffmpeg = _require_ffmpeg()
    paths = sorted(args.videos_dir.rglob("*.mp4"))
    if args.video_id:
        paths = [p for p in paths if _video_id_from_path(p) == args.video_id]
        if not paths:
            raise SystemExit(f"No local file for video_id {args.video_id}")

    total = len(paths)
    print(f"Migrating {total} video(s) to HLS (jobs={args.jobs}, force={args.force})", flush=True)

    ok = fail = 0
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {
            pool.submit(process_video, path, ffmpeg, force=args.force, index=i, total=total): path
            for i, path in enumerate(paths, 1)
        }
        for fut in as_completed(futures):
            path = futures[fut]
            try:
                fut.result()
                ok += 1
            except (S3Error, subprocess.CalledProcessError, OSError) as e:
                fail += 1
                msg = f"  FAIL {path.name}: {e}"
                errors.append(msg)
                with _print_lock:
                    print(msg, flush=True)

    print(f"Done: ok={ok} fail={fail} total={total}", flush=True)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
