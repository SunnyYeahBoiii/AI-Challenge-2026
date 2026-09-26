#!/usr/bin/env python3
"""Package source videos into HLS fragmented-MP4 playlists using stream copy.

Reads .mp4/.mov sources recursively, writes OUT/<group>/<video_id>/{index.m3u8,
init.mp4, segNNNNN.m4s}. Each video is built in a hidden .<video_id>.part directory
and renamed into place only after validation, so OUT never contains a partial video.
Source files are only read, never written, moved or transcoded.
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

VIDEO_SUFFIXES = frozenset({".mp4", ".mov"})
PLAYLIST_NAME = "index.m3u8"
INIT_NAME = "init.mp4"
SEGMENT_NAME = "seg%05d.m4s"
SEGMENT_TARGET_SECONDS = 6
DURATION_TOLERANCE_SECONDS = 2.0
RESERVED_FREE_BYTES = 8 * 1024**3
HEVC_CODECS = frozenset({"hevc", "h265"})
DEFAULT_JOBS = 4
GIB = 1024**3
PROBE_TIMEOUT_SECONDS = 120
ENCODE_TIMEOUT_SECONDS = 3600

STATUS_OK = "OK"
STATUS_SKIP = "SKIP"
STATUS_HEVC = "HEVC"
STATUS_SPACE = "SPACE"
STATUS_FAIL = "FAIL"

_print_lock = threading.Lock()


@dataclass(frozen=True)
class Video:
    """A source video to package, with its output group and id resolved."""

    path: Path
    group: str
    video_id: str

    @property
    def size_bytes(self) -> int:
        return self.path.stat().st_size


@dataclass(frozen=True)
class Outcome:
    """Result of packaging one video."""

    status: str
    video_id: str
    detail: str = ""


def log(message: str) -> None:
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    with _print_lock:
        print(f"{stamp} {message}", flush=True)


def human_bytes(num_bytes: int) -> str:
    return f"{num_bytes / GIB:.2f}GiB"


def split_ids(raw: str) -> list[str]:
    return raw.replace(",", " ").split()


def find_videos(src: Path, only: list[str], prefix: str | None, limit: int) -> list[Video]:
    """Collect source videos in deterministic order, then apply filters."""
    if not src.is_dir():
        raise SystemExit(f"source directory not found: {src}")

    found = [
        path
        for path in src.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    ]
    found.sort(key=lambda path: path.relative_to(src).as_posix())

    wanted = set(only)
    videos: list[Video] = []
    for path in found:
        video_id = path.stem
        if wanted and video_id not in wanted:
            continue
        if prefix and not video_id.startswith(prefix):
            continue
        group = video_id.split("_", 1)[0].split("-", 1)[0]
        videos.append(Video(path=path, group=group, video_id=video_id))

    return videos[:limit] if limit > 0 else videos


def run_command(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def probe_codec(path: Path) -> str:
    """Return the first video stream codec name, or an empty string on failure."""
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
            str(path),
        ],
        PROBE_TIMEOUT_SECONDS,
    )
    return result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""


def probe_duration(path: Path) -> float:
    """Return the container duration in seconds."""
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        PROBE_TIMEOUT_SECONDS,
    )
    raw = result.stdout.strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"unreadable source duration {raw!r}") from exc


def playlist_duration(playlist: Path) -> tuple[float, int]:
    """Return (total seconds, segment count) summed from EXTINF entries."""
    total = 0.0
    count = 0
    for line in playlist.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#EXTINF:"):
            continue
        value = line[len("#EXTINF:") :].split(",", 1)[0]
        try:
            total += float(value)
        except ValueError:
            continue
        count += 1
    return total, count


def segment_references(playlist: Path) -> list[str]:
    return [
        line.strip()
        for line in playlist.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def validate_output(tmp_dir: Path, src_duration: float) -> str:
    """Validate a finished temp output. Returns a detail string or raises RuntimeError."""
    playlist = tmp_dir / PLAYLIST_NAME
    init = tmp_dir / INIT_NAME
    if not playlist.is_file():
        raise RuntimeError(f"missing {PLAYLIST_NAME}")
    if not init.is_file() or init.stat().st_size == 0:
        raise RuntimeError(f"missing or empty {INIT_NAME}")

    text = playlist.read_text(encoding="utf-8")
    if "#EXT-X-ENDLIST" not in text:
        raise RuntimeError("playlist is not a complete VOD playlist")
    if "#EXT-X-MAP" not in text:
        raise RuntimeError("playlist has no EXT-X-MAP init segment")

    refs = segment_references(playlist)
    if not refs:
        raise RuntimeError("playlist references no segments")
    for ref in refs:
        seg = tmp_dir / ref
        if not seg.is_file() or seg.stat().st_size == 0:
            raise RuntimeError(f"missing or empty segment {ref}")

    out_duration, counted = playlist_duration(playlist)
    if counted != len(refs):
        raise RuntimeError(f"EXTINF count {counted} != segment count {len(refs)}")
    delta = abs(out_duration - src_duration)
    if delta > DURATION_TOLERANCE_SECONDS:
        raise RuntimeError(
            f"duration mismatch src={src_duration:.2f}s out={out_duration:.2f}s "
            f"delta={delta:.2f}s > {DURATION_TOLERANCE_SECONDS:.0f}s"
        )
    return (
        f"segments={len(refs)} src={src_duration:.2f}s out={out_duration:.2f}s "
        f"delta={delta:.2f}s size={human_bytes(dir_size(tmp_dir))}"
    )


def dir_size(path: Path) -> int:
    return sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file())


def free_bytes(target: Path) -> int:
    """Free bytes on the filesystem that contains target."""
    probe = target
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            break
        probe = parent
    return shutil.disk_usage(probe).free


def build_command(src: Path, tmp_dir: Path) -> list[str]:
    return [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c",
        "copy",
        "-f",
        "hls",
        "-hls_time",
        str(SEGMENT_TARGET_SECONDS),
        "-hls_list_size",
        "0",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_type",
        "fmp4",
        "-hls_fmp4_init_filename",
        INIT_NAME,
        "-hls_segment_filename",
        str(tmp_dir / SEGMENT_NAME),
        "-hls_flags",
        "independent_segments",
        str(tmp_dir / PLAYLIST_NAME),
    ]


def package_video(video: Video, out_root: Path) -> Outcome:
    final_dir = out_root / video.group / video.video_id
    if (final_dir / PLAYLIST_NAME).is_file():
        return Outcome(STATUS_SKIP, video.video_id, "already packaged")

    codec = probe_codec(video.path)
    if codec.lower() in HEVC_CODECS:
        return Outcome(STATUS_HEVC, video.video_id, f"codec={codec or 'unknown'}")

    needed = video.size_bytes + RESERVED_FREE_BYTES
    free = free_bytes(out_root)
    if free < needed:
        return Outcome(
            STATUS_SPACE,
            video.video_id,
            f"free={human_bytes(free)} need={human_bytes(needed)} "
            f"(source={human_bytes(video.size_bytes)} + "
            f"reserve={human_bytes(RESERVED_FREE_BYTES)})",
        )

    parent = final_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = parent / f".{video.video_id}.part"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()

    try:
        src_duration = probe_duration(video.path)
        result = run_command(build_command(video.path, tmp_dir), ENCODE_TIMEOUT_SECONDS)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()[-3:]
            raise RuntimeError(f"ffmpeg exit {result.returncode}: {' | '.join(tail)}")
        detail = validate_output(tmp_dir, src_duration)
        if final_dir.exists():
            shutil.rmtree(tmp_dir)
            return Outcome(STATUS_SKIP, video.video_id, "appeared concurrently")
        tmp_dir.rename(final_dir)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return Outcome(STATUS_FAIL, video.video_id, str(exc)[:400])

    return Outcome(STATUS_OK, video.video_id, detail)


def report(outcome: Outcome) -> None:
    detail = f" {outcome.detail}" if outcome.detail else ""
    log(f"{outcome.status} {outcome.video_id}{detail}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package videos into HLS fMP4 (ffmpeg -c copy).",
    )
    parser.add_argument("--src", type=Path, default=Path("data/video"), help="source root")
    parser.add_argument("--out", type=Path, default=Path("data/hls"), help="output root")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="parallel videos")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="only these video ids (repeatable or comma separated)",
    )
    parser.add_argument("--prefix", default=None, help="only video ids starting with this")
    parser.add_argument("--limit", type=int, default=0, help="max videos, 0 = unlimited")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    only: list[str] = [vid for raw in args.only for vid in split_ids(raw)]
    videos = find_videos(args.src, only, args.prefix, args.limit)

    args.out.mkdir(parents=True, exist_ok=True)
    limit_text = args.limit or "none"
    free_text = human_bytes(free_bytes(args.out))
    log(
        f"START src={args.src} out={args.out} jobs={args.jobs} "
        f"prefix={args.prefix or '-'} limit={limit_text} "
        f"selected={len(videos)} free={free_text}"
    )
    if not videos:
        log("DONE selected=0 ok=0 skip=0 hevc=0 space=0 fail=0")
        return 0

    counts = {STATUS_OK: 0, STATUS_SKIP: 0, STATUS_HEVC: 0, STATUS_SPACE: 0, STATUS_FAIL: 0}
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for outcome in pool.map(lambda video: package_video(video, args.out), videos):
            counts[outcome.status] = counts.get(outcome.status, 0) + 1
            report(outcome)

    log(
        f"DONE selected={len(videos)} ok={counts[STATUS_OK]} skip={counts[STATUS_SKIP]} "
        f"hevc={counts[STATUS_HEVC]} space={counts[STATUS_SPACE]} fail={counts[STATUS_FAIL]}"
    )
    return 1 if counts[STATUS_FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
