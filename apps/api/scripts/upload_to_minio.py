"""
Upload local keyframes + video files to MinIO, mirroring the key layout that
app/services/storage.py builds public URLs from:

    keyframes bucket: {level}/{video_id}/{frame_index}.webp   (level = video_id[:3])
    videos bucket:     {level}/{video_id}.mp4

Buckets are created (if missing) with a public-read policy, since storage.py
returns plain path-style URLs rather than presigned ones.

Progressive playback requires the MP4 `moov` atom at the start of the file
(`ffmpeg -movflags +faststart`). Without that, browsers must download nearly
the whole object before they can seek/play — Range requests alone are not enough.
Pass `--faststart` to remux each video (stream copy, no re-encode) before upload.

Usage:
    cd apps/api
    uv run python scripts/upload_to_minio.py --keyframes
    uv run python scripts/upload_to_minio.py --videos /path/to/videos --faststart --jobs 8
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
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
MINIO_BUCKET_KEYFRAMES = os.getenv("MINIO_BUCKET_KEYFRAMES", "keyframes")
MINIO_BUCKET_VIDEOS = os.getenv("MINIO_BUCKET_VIDEOS", "videos")

KEYFRAMES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "keyframes" / "keyframes"

_print_lock = threading.Lock()


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


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit(
            "ffmpeg not found on PATH. Install it (e.g. `brew install ffmpeg`) "
            "or omit --faststart."
        )
    return ffmpeg


def remux_faststart(src: Path, dest: Path, ffmpeg: str) -> None:
    """Rewrite MP4 with moov at the front (no re-encode)."""
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(src),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(dest),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _local_needs_faststart(path: Path, probe_bytes: int = 512 * 1024) -> bool:
    """True if moov is missing from the first probe window (typical end-moov MP4)."""
    size = path.stat().st_size
    if size <= 0:
        return False
    with path.open("rb") as f:
        head = f.read(min(probe_bytes, size))
    moov = head.find(b"moov")
    if moov < 0:
        return True
    return moov > int(size * 0.08)


def _done_keys_from_log(log_path: Path) -> set[str]:
    """Parse keys already uploaded from a previous run's log lines."""
    if not log_path.is_file():
        return set()
    keys: set[str] = set()
    # e.g. "  [12] L29/L29_V016.mp4 (faststart)"
    pat = re.compile(r"\]\s+(\S+\.mp4)")
    for line in log_path.read_text(errors="ignore").splitlines():
        m = pat.search(line)
        if m:
            keys.add(m.group(1))
    return keys


def _put_with_retry(
    client: Minio,
    bucket: str,
    key: str,
    file_path: Path,
    *,
    attempts: int = 4,
) -> None:
    """Upload with retries — Cloudflare often returns 524 under heavy parallel load."""
    import time

    last: BaseException | None = None
    for i in range(attempts):
        try:
            client.fput_object(
                bucket,
                key,
                str(file_path),
                content_type="video/mp4",
                metadata={"Cache-Control": "public, max-age=300"},
            )
            return
        except Exception as exc:  # noqa: BLE001 — network/CDN errors vary by type
            last = exc
            wait = 2 ** i
            with _print_lock:
                print(f"  retry {i + 1}/{attempts} {key}: {exc} (sleep {wait}s)", flush=True)
            time.sleep(wait)
    assert last is not None
    raise last


def _upload_one(
    path: Path,
    *,
    bucket: str,
    faststart: bool,
    ffmpeg: str,
    index: int,
    total: int,
) -> str:
    video_id = _video_id_from_path(path)
    level = video_id[:3]
    key = f"{level}/{video_id}.mp4"
    client = _client()  # one client per task — safer across threads

    if faststart and _local_needs_faststart(path):
        with tempfile.TemporaryDirectory(prefix="faststart_") as tmp:
            out = Path(tmp) / path.name
            remux_faststart(path, out, ffmpeg)
            _put_with_retry(client, bucket, key, out)
        tag = "faststart"
    elif faststart:
        # Already has moov near the front — upload as-is.
        _put_with_retry(client, bucket, key, path)
        tag = "already-faststart"
    else:
        _put_with_retry(client, bucket, key, path)
        tag = "raw"

    msg = f"  [{index}/{total}] {key} ({tag})"
    with _print_lock:
        print(msg, flush=True)
    return key


def upload_videos(
    videos_dir: Path,
    *,
    faststart: bool,
    jobs: int,
    skip_keys: set[str],
) -> int:
    bucket = MINIO_BUCKET_VIDEOS
    _ensure_bucket(_client(), bucket)
    ffmpeg = _require_ffmpeg() if faststart else ""

    paths = sorted(videos_dir.rglob("*.mp4"))
    todo: list[Path] = []
    skipped = 0
    for path in paths:
        video_id = _video_id_from_path(path)
        key = f"{video_id[:3]}/{video_id}.mp4"
        if key in skip_keys:
            skipped += 1
            continue
        todo.append(path)

    total = len(todo)
    print(
        f"Uploading {total} videos "
        f"(skipped {skipped} already done, jobs={jobs}, faststart={faststart})",
        flush=True,
    )
    if total == 0:
        return 0

    ok = 0
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {
            pool.submit(
                _upload_one,
                path,
                bucket=bucket,
                faststart=faststart,
                ffmpeg=ffmpeg,
                index=i,
                total=total,
            ): path
            for i, path in enumerate(todo, 1)
        }
        for fut in as_completed(futures):
            path = futures[fut]
            try:
                fut.result()
                ok += 1
            except Exception as e:  # noqa: BLE001 — keep other workers alive on CDN blips
                msg = f"  FAIL {path.name}: {e}"
                errors.append(msg)
                with _print_lock:
                    print(msg, flush=True)

    if errors:
        print(f"Finished with {len(errors)} failures; ok={ok}/{total}", flush=True)
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload keyframes/videos to MinIO")
    parser.add_argument("--keyframes", action="store_true", help=f"Upload {KEYFRAMES_DIR}")
    parser.add_argument("--videos", type=Path, help="Directory of source .mp4 files to upload")
    parser.add_argument(
        "--faststart",
        action="store_true",
        help="Remux videos with ffmpeg -movflags +faststart before upload (needed for Range streaming)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Parallel remux+upload workers (default: 1). Try 6–8 on a fast uplink.",
    )
    parser.add_argument(
        "--skip-from-log",
        type=Path,
        help="Skip keys already listed as uploaded in this log (resume)",
    )
    args = parser.parse_args()

    if not args.keyframes and not args.videos:
        raise SystemExit("Nothing to do: pass --keyframes and/or --videos <dir>")

    try:
        if args.keyframes:
            n = upload_keyframes(_client())
            print(f"Done: {n} keyframes -> bucket '{MINIO_BUCKET_KEYFRAMES}'")
        if args.videos:
            if not args.videos.is_dir():
                raise SystemExit(f"Not a directory: {args.videos}")
            skip = _done_keys_from_log(args.skip_from_log) if args.skip_from_log else set()
            n = upload_videos(
                args.videos,
                faststart=args.faststart,
                jobs=args.jobs,
                skip_keys=skip,
            )
            print(f"Done: {n} videos -> bucket '{MINIO_BUCKET_VIDEOS}'")
    except S3Error as e:
        raise SystemExit(f"MinIO error: {e}")
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"ffmpeg failed: {e}") from e


if __name__ == "__main__":
    main()
