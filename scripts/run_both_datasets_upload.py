#!/usr/bin/env python3
"""Wait until BOTH Kaggle datasets are fully downloaded, then organize + upload.

Datasets (required — will not proceed with only one):
  1) thnhvlngc/video-part2-batch1-aic25
  2) tunvln/l21-24-dataset-aic

Does not start a competing download while the existing kagglehub job is running.
Polls cache dirs until both are extracted (no leftover *.archive).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ORGANIZE = REPO_ROOT / "scripts" / "organize_and_upload_videos.py"
CACHE_ROOT = Path.home() / ".cache" / "kagglehub" / "datasets"

DATASETS = (
    ("thnhvlngc", "video-part2-batch1-aic25"),
    ("tunvln", "l21-24-dataset-aic"),
)

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def dataset_dir(owner: str, name: str) -> Path:
    return CACHE_ROOT / owner / name


def is_ready(owner: str, name: str) -> tuple[bool, str]:
    root = dataset_dir(owner, name)
    if not root.exists():
        return False, "missing cache dir"
    archives = list(root.glob("*.archive")) + list(root.rglob("*.archive"))
    if archives:
        sizes = ", ".join(f"{p.name}={p.stat().st_size/1e9:.2f}G" for p in archives[:3])
        return False, f"still downloading ({sizes})"
    # Prefer versioned extract dirs like .../1/
    candidates = [p for p in root.iterdir() if p.is_dir()]
    search_roots = candidates or [root]
    video_count = 0
    for base in search_roots:
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
                video_count += 1
    if video_count == 0:
        return False, "extracted but no videos yet"
    return True, f"{video_count} videos"


def resolve_source(owner: str, name: str) -> Path:
    root = dataset_dir(owner, name)
    # kagglehub usually extracts to <root>/<version>/
    versions = sorted(
        (p for p in root.iterdir() if p.is_dir() and p.name.isdigit()),
        key=lambda p: int(p.name),
    )
    return versions[-1] if versions else root


def wait_both(poll_sec: float) -> list[Path]:
    while True:
        statuses = []
        all_ok = True
        for owner, name in DATASETS:
            ok, msg = is_ready(owner, name)
            statuses.append(f"{owner}/{name}: {'OK' if ok else 'WAIT'} ({msg})")
            all_ok = all_ok and ok
        print(" | ".join(statuses), flush=True)
        if all_ok:
            return [resolve_source(o, n) for o, n in DATASETS]
        time.sleep(poll_sec)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--poll-sec", type=float, default=60.0)
    parser.add_argument(
        "--now",
        action="store_true",
        help="Do not wait — fail if either dataset is incomplete",
    )
    args = parser.parse_args()

    if args.now:
        paths = []
        for owner, name in DATASETS:
            ok, msg = is_ready(owner, name)
            print(f"{owner}/{name}: {'OK' if ok else 'FAIL'} ({msg})")
            if not ok:
                print("Refusing to continue — both datasets required.", file=sys.stderr)
                return 1
            paths.append(resolve_source(owner, name))
    else:
        print("Waiting until BOTH datasets are fully downloaded...", flush=True)
        paths = wait_both(args.poll_sec)

    for path in paths:
        print(f"SOURCE {path}", flush=True)

    cmd = [
        sys.executable,
        str(ORGANIZE),
        *[str(p) for p in paths],
        "--group-style",
        "L21",
    ]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.skip_upload:
        cmd.append("--skip-upload")

    print("Running:", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)
    print("Done: both datasets organized under L21/... and uploaded to MinIO videos.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
