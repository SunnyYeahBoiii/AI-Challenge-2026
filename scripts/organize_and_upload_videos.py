#!/usr/bin/env python3
"""Organize downloaded AIC videos into Lxx/ groups and upload to MinIO.

Expected video filenames: L21_V001.mp4, L22_V013.mp4, ...
Output layout (default, matches keyframes):
  data/videos_grouped/L21/L21_V001.mp4
  data/videos_grouped/L22/L22_V001.mp4

Upload target: myminio/videos/L21/... via local /tmp/mc (alias -> 100.115.213.89:9000).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

VIDEO_RE = re.compile(r"^(L)(\d+)(_V\d+.*)$", re.IGNORECASE)
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "videos_grouped"
DEFAULT_MC = Path("/tmp/mc")
DEFAULT_ALIAS = "myminio"
DEFAULT_BUCKET = "videos"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "sources",
        nargs="+",
        type=Path,
        help="Directories that contain downloaded videos (kagglehub extract paths)",
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--group-style",
        choices=("L21", "L_21"),
        default="L21",
        help="Folder naming: L21 (matches keyframes) or L_21",
    )
    p.add_argument(
        "--link",
        choices=("hardlink", "symlink", "copy", "move"),
        default="hardlink",
        help="How to place files into group folders (hardlink saves disk)",
    )
    p.add_argument("--mc", type=Path, default=DEFAULT_MC)
    p.add_argument("--alias", default=DEFAULT_ALIAS)
    p.add_argument("--bucket", default=DEFAULT_BUCKET)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-upload", action="store_true")
    return p.parse_args()


def group_folder_name(prefix: str, num: str, style: str) -> str:
    # Confirmed: use L21 (not L_21) to match keyframes layout.
    if style == "L_21":
        return f"{prefix}_{num}"
    return f"{prefix}{num}"


def find_videos(sources: list[Path]) -> list[Path]:
    found: list[Path] = []
    for src in sources:
        if not src.exists():
            raise FileNotFoundError(src)
        for path in src.rglob("*"):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
                found.append(path)
    return sorted(found)


def place_file(src: Path, dest: Path, mode: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [{mode}] {src} -> {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    if mode == "hardlink":
        try:
            os.link(src, dest)
        except OSError:
            shutil.copy2(src, dest)
    elif mode == "symlink":
        os.symlink(src.resolve(), dest)
    elif mode == "copy":
        shutil.copy2(src, dest)
    elif mode == "move":
        shutil.move(str(src), str(dest))
    else:
        raise ValueError(mode)


def organize(
    videos: list[Path],
    out: Path,
    style: str,
    link_mode: str,
    dry_run: bool,
) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    skipped: list[Path] = []

    for video in videos:
        m = VIDEO_RE.match(video.stem)
        if not m:
            skipped.append(video)
            continue
        prefix, num, _rest = m.group(1).upper(), m.group(2), m.group(3)
        folder = group_folder_name(prefix, num, style)
        dest = out / folder / video.name
        place_file(video, dest, link_mode, dry_run)
        groups[folder].append(dest if not dry_run else video)

    print(f"Organized {sum(len(v) for v in groups.values())} videos into {len(groups)} groups")
    for folder in sorted(groups):
        print(f"  {folder}: {len(groups[folder])} files")
    if skipped:
        print(f"Skipped {len(skipped)} files without Lxx_Vyy name:")
        for path in skipped[:20]:
            print(f"  - {path.name}")
        if len(skipped) > 20:
            print(f"  ... and {len(skipped) - 20} more")
    return groups


def upload(out: Path, mc: Path, alias: str, bucket: str, dry_run: bool) -> None:
    if not mc.exists():
        raise FileNotFoundError(f"mc binary not found: {mc}")
    target = f"{alias}/{bucket}/"
    cmd = [str(mc), "mirror", "--overwrite", "--exclude", ".DS_Store", f"{out}/", target]
    print("Upload command:", " ".join(cmd))
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def main() -> int:
    args = parse_args()
    videos = find_videos(args.sources)
    print(f"Found {len(videos)} video files under {len(args.sources)} source(s)")
    if not videos:
        print("No videos found — aborting", file=sys.stderr)
        return 1

    organize(videos, args.out, args.group_style, args.link, args.dry_run)

    if not args.skip_upload:
        # MinIO drive on sunny@100.115.213.89 is ~221GiB; watch free space before large mirrors.
        upload(args.out, args.mc, args.alias, args.bucket, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
