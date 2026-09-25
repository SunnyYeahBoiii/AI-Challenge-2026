"""Remux videos so the moov atom sits at the file start (lossless, no re-encode).

Source mp4/mov here have `moov` at the END, so a browser must fetch the file tail
before it can play or seek. `-c copy -movflags +faststart` moves it to the front in
seconds per file. Output mirrors data/videos_grouped into data/videos_faststart and
the API prefers those copies automatically. Originals are never touched.

    PYTHONPATH=. uv run python scripts/faststart_videos.py [--jobs 4] [--group N0]
"""

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import DEFAULT_VIDEOS_DIR, DEFAULT_VIDEOS_FASTSTART_DIR


def remux(src: Path, dst: Path) -> str:
    if dst.exists():
        return f"skip  {src.name}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.part")
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-i", str(src),
        "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
        "-movflags", "+faststart", "-f", "mp4", str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        return f"FAIL  {src.name}: {r.stderr.strip()[:200]}"
    tmp.rename(dst)
    return f"ok    {src.name}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_VIDEOS_DIR)
    ap.add_argument("--dst", type=Path, default=DEFAULT_VIDEOS_FASTSTART_DIR)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--group", default="", help="only groups whose name starts with this")
    args = ap.parse_args()

    files = sorted(
        f for g in args.src.iterdir() if g.is_dir() and g.name.startswith(args.group)
        for f in g.iterdir()
        if f.suffix.lower() in {".mp4", ".mov"} and not f.name.startswith(".")
    )
    print(f"{len(files)} files")
    with ThreadPoolExecutor(args.jobs) as ex:
        for msg in ex.map(lambda f: remux(f, args.dst / f.parent.name / f"{f.stem}.mp4"), files):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
