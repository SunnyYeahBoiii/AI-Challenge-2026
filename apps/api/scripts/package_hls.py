"""Package mp4/mov into local HLS (fMP4, ~6s segments) with `-c copy` (no re-encode); HEVC sources are re-encoded to h264.

Segments can only be cut at source keyframes, so this suits sources whose keyframes are
<= ~6s apart (checked for group S01: 3-6s). Source is data/videos_grouped by default, or
the output of transcode_heavy_videos.py (--src data/videos_faststart). Writes data/videos_hls/<group>/<id>/{index.m3u8,init.mp4,segNNNNN.m4s}.
The API then serves it at /api/videos/<id>/hls/index.m3u8. A package is committed by renaming
its temp dir only after ffmpeg succeeds, so half-built ones are never served.

    PYTHONPATH=. uv run python scripts/package_hls.py --group S01 --jobs 4
"""

import argparse
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import DEFAULT_VIDEOS_DIR, DEFAULT_VIDEOS_HLS_DIR

SEGMENT_SECONDS = 6


def duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip() or 0)


def video_codec(path: Path) -> str:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


# HEVC does not play in Chrome/Firefox: re-encode those to h264 (keyframe every 2s), keep resolution.
_HEVC_ENCODE = [
    "-c:v", "h264_videotoolbox", "-b:v", "5000k", "-maxrate", "7000k", "-bufsize", "10000k",
    "-g", "50", "-force_key_frames", "expr:gte(t,n_forced*2)", "-c:a", "aac", "-b:a", "96k",
]


def package(src: Path, out: Path) -> str:
    if (out / "index.m3u8").exists():
        return f"skip  {src.name}"
    tmp = out.with_name(f".{out.name}.part")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-i", str(src),
        *(_HEVC_ENCODE if video_codec(src) == "hevc" else ["-c", "copy"]),
        "-f", "hls", "-hls_time", str(SEGMENT_SECONDS), "-hls_playlist_type", "vod",
        "-hls_segment_type", "fmp4", "-hls_fmp4_init_filename", "init.mp4",
        "-hls_flags", "independent_segments",
        "-hls_segment_filename", str(tmp / "seg%05d.m4s"), str(tmp / "index.m3u8"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return f"FAIL  {src.name}: {r.stderr.strip()[-200:]}"
    src_dur, hls_dur = duration(src), duration(tmp / "index.m3u8")
    if abs(src_dur - hls_dur) > 2:
        shutil.rmtree(tmp, ignore_errors=True)
        return f"FAIL  {src.name}: duration mismatch {hls_dur:.1f}s vs {src_dur:.1f}s"
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    return f"ok    {src.name} {len(list(out.glob('seg*.m4s')))} segments"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_VIDEOS_DIR)
    ap.add_argument("--dst", type=Path, default=DEFAULT_VIDEOS_HLS_DIR)
    ap.add_argument("--group", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()

    files = sorted(
        f for f in (args.src / args.group).iterdir()
        if f.suffix.lower() in {".mp4", ".mov"} and not f.name.startswith(".")
    )
    print(f"{len(files)} files", flush=True)
    with ThreadPoolExecutor(args.jobs) as ex:
        for msg in ex.map(lambda f: package(f, args.dst / args.group / f.stem), files):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
