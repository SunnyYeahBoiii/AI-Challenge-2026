"""Transcode heavy/odd-codec videos to seek-friendly h264 720p (keyframe every 2s).

Targets long AV1/HEVC recordings (group S01: 2-6h, up to 9GB) that stall on seek or
do not play in Safari/Chrome. Output goes to data/videos_faststart/<group>/<id>.mp4,
which the API prefers over the original; originals are never touched.

Uses Apple VideoToolbox (hardware). A file is only committed after the output
duration matches the source, so a crash never leaves a half-written video live.

    PYTHONPATH=. uv run python scripts/transcode_heavy_videos.py --group S01 --jobs 2
"""

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import DEFAULT_VIDEOS_DIR, DEFAULT_VIDEOS_FASTSTART_DIR

GOP_SECONDS = 2


def duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip() or 0)


def transcode(src: Path, dst: Path, bitrate: str) -> str:
    if dst.exists() and dst.stat().st_size > 0:
        return f"skip  {src.name}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.part")
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-i", str(src),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", "scale=-2:720",
        "-c:v", "h264_videotoolbox", "-b:v", bitrate, "-maxrate", "2500k", "-bufsize", "5000k",
        "-g", str(30 * GOP_SECONDS), "-force_key_frames", f"expr:gte(t,n_forced*{GOP_SECONDS})",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart", "-f", "mp4", str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        return f"FAIL  {src.name}: {r.stderr.strip()[-200:]}"
    if abs(duration(tmp) - duration(src)) > 2:
        tmp.unlink(missing_ok=True)
        return f"FAIL  {src.name}: duration mismatch {duration(tmp):.1f}s vs {duration(src):.1f}s"
    tmp.rename(dst)
    return f"ok    {src.name} {dst.stat().st_size / 1e9:.2f}GB"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_VIDEOS_DIR)
    ap.add_argument("--dst", type=Path, default=DEFAULT_VIDEOS_FASTSTART_DIR)
    ap.add_argument("--group", required=True, help="group folder name, e.g. S01")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--only", nargs="*", default=[], help="only these video ids (stems), e.g. S01-V009")
    ap.add_argument("--bitrate", default="1800k")
    args = ap.parse_args()

    files = sorted(
        f for f in (args.src / args.group).iterdir()
        if f.suffix.lower() in {".mp4", ".mov"} and not f.name.startswith(".")
        and (not args.only or f.stem in args.only)
    )
    print(f"{len(files)} files", flush=True)
    with ThreadPoolExecutor(args.jobs) as ex:
        for msg in ex.map(lambda f: transcode(f, args.dst / args.group / f"{f.stem}.mp4", args.bitrate), files):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
