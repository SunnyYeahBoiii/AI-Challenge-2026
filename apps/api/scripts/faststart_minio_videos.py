"""
Remux existing MinIO MP4s in-place with `ffmpeg -movflags +faststart`.

AIC source videos typically have `moov` at the end of the file. Browsers must
then download almost the entire object before playback/seek can start, even
when the server supports HTTP Range. This script stream-copies each object so
`moov` is at the front; after that, progressive Range streaming works.

Downloads use the public path-style HTTPS URL (Cloudflare often AccessDenied
authenticated GetObject). Uploads use the MinIO SDK with credentials from .env.

Requires: ffmpeg on PATH, MinIO credentials in apps/api/.env

Usage:
    cd apps/api
    uv run python scripts/faststart_minio_videos.py --video-id L26_V211 --dry-run
    uv run python scripts/faststart_minio_videos.py --video-id L26_V211
    uv run python scripts/faststart_minio_videos.py --prefix L26/
    uv run python scripts/faststart_minio_videos.py --all
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
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

_PROBE_BYTES = 512 * 1024
_HTTP_UA = "FrameSeeker/1.0 (faststart-remux)"


def _client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def _public_url(key: str) -> str:
    scheme = "https" if MINIO_SECURE else "http"
    return f"{scheme}://{MINIO_ENDPOINT}/{MINIO_BUCKET_VIDEOS}/{key}"


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg not found. Install with `brew install ffmpeg`.")
    return ffmpeg


def _http_get(url: str, *, dest: Path | None = None, range_header: str | None = None) -> tuple[int, dict[str, str]]:
    headers = {"User-Agent": _HTTP_UA}
    if range_header:
        headers["Range"] = range_header
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=600) as resp:
        status = getattr(resp, "status", 200)
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
        if dest is None:
            resp.read()
            return status, hdrs
        with dest.open("wb") as out:
            shutil.copyfileobj(resp, out)
        return status, hdrs


def _object_size_and_moov(key: str) -> tuple[int, int | None]:
    """Probe object size + moov offset using a small public Range GET."""
    url = _public_url(key)
    with tempfile.NamedTemporaryFile(prefix="moov_probe_") as tmp:
        status, hdrs = _http_get(url, dest=Path(tmp.name), range_header=f"bytes=0-{_PROBE_BYTES - 1}")
        data = Path(tmp.name).read_bytes()
    cr = hdrs.get("content-range", "")
    # content-range: bytes 0-N/TOTAL
    size = int(cr.rsplit("/", 1)[-1]) if "/" in cr else len(data)
    moov = data.find(b"moov")
    return size, (moov if moov >= 0 else None)


def _needs_faststart(size: int, moov_offset: int | None) -> bool:
    if size <= 0 or moov_offset is None:
        # moov not in the first probe window ⇒ almost certainly at the end
        return True
    return moov_offset > int(size * 0.08)


def remux_faststart(src: Path, dest: Path, ffmpeg: str) -> None:
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


def iter_keys(client: Minio, *, prefix: str, video_id: str | None, all_objects: bool) -> list[str]:
    if video_id:
        return [f"{video_id[:3]}/{video_id}.mp4"]
    if not all_objects and not prefix:
        raise SystemExit("Pass --video-id, --prefix, or --all")
    return [
        obj.object_name
        for obj in client.list_objects(MINIO_BUCKET_VIDEOS, prefix=prefix, recursive=True)
        if obj.object_name and obj.object_name.endswith(".mp4")
    ]


def process_key(client: Minio, key: str, ffmpeg: str, *, dry_run: bool, force: bool) -> str:
    size, moov = _object_size_and_moov(key)
    if not force and not _needs_faststart(size, moov):
        return f"skip {key} (moov@{moov}/{size})"
    if dry_run:
        return f"dry-run {key} moov@{moov}/{size}"

    with tempfile.TemporaryDirectory(prefix="faststart_minio_") as tmp:
        tmp_dir = Path(tmp)
        src = tmp_dir / "src.mp4"
        dest = tmp_dir / "faststart.mp4"
        _http_get(_public_url(key), dest=src)
        remux_faststart(src, dest, ffmpeg)
        # Shorter CDN TTL so remuxed objects replace stale Cloudflare HIT sooner.
        client.fput_object(
            MINIO_BUCKET_VIDEOS,
            key,
            str(dest),
            content_type="video/mp4",
            metadata={"Cache-Control": "public, max-age=300"},
        )
        return f"ok {key} ({src.stat().st_size} -> {dest.stat().st_size} bytes)"


def main() -> None:
    parser = argparse.ArgumentParser(description="faststart remux for MinIO videos")
    parser.add_argument("--video-id", help="Single video id, e.g. L26_V211")
    parser.add_argument("--prefix", default="", help="Only keys under this prefix, e.g. L26/")
    parser.add_argument("--all", action="store_true", help="Process entire videos bucket")
    parser.add_argument("--dry-run", action="store_true", help="Inspect only, do not upload")
    parser.add_argument("--force", action="store_true", help="Remux even if moov looks early")
    args = parser.parse_args()

    ffmpeg = _require_ffmpeg()
    client = _client()
    try:
        keys = iter_keys(
            client,
            prefix=args.prefix,
            video_id=args.video_id,
            all_objects=args.all,
        )
    except S3Error as e:
        raise SystemExit(f"MinIO list error: {e}") from e

    if not keys:
        raise SystemExit("No matching .mp4 keys")

    print(f"Processing {len(keys)} object(s) in bucket '{MINIO_BUCKET_VIDEOS}'", flush=True)
    ok = skip = fail = 0
    for i, key in enumerate(keys, 1):
        try:
            msg = process_key(client, key, ffmpeg, dry_run=args.dry_run, force=args.force)
            if msg.startswith("ok"):
                ok += 1
            elif msg.startswith("skip"):
                skip += 1
        except (S3Error, subprocess.CalledProcessError, OSError, urllib.error.URLError, ValueError) as e:
            msg = f"FAIL {key}: {e}"
            fail += 1
        print(f"  [{i}/{len(keys)}] {msg}", flush=True)

    print(f"Done: ok={ok} skip={skip} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
