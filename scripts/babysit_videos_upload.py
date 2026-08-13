#!/usr/bin/env python3
"""Overnight babysitter: wait for BOTH Kaggle video datasets, organize L21/..., upload MinIO.

Safe to leave running while asleep. Logs to scripts/logs/babysit-videos.log
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / "scripts" / "logs"
LOG_FILE = LOG_DIR / "babysit-videos.log"
STATUS_FILE = LOG_DIR / "babysit-videos.status"
RUNNER = REPO_ROOT / "scripts" / "run_both_datasets_upload.py"
ORGANIZE = REPO_ROOT / "scripts" / "organize_and_upload_videos.py"

CACHE_ROOT = Path.home() / ".cache" / "kagglehub" / "datasets"
DATASETS = (
    ("thnhvlngc", "video-part2-batch1-aic25"),
    ("tunvln", "l21-24-dataset-aic"),
)
SLUGS = (
    "thnhvlngc/video-part2-batch1-aic25",
    "tunvln/l21-24-dataset-aic",
)
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
DOWNLOAD_PID_HINT = 38946
POLL_SEC = 120


def log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    STATUS_FILE.write_text(line + "\n", encoding="utf-8")


def pid_alive(pid: int) -> bool:
    try:
        subprocess.run(["ps", "-p", str(pid)], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def dataset_ready(owner: str, name: str) -> tuple[bool, str]:
    root = CACHE_ROOT / owner / name
    if not root.exists():
        return False, "missing"
    archives = list(root.glob("*.archive")) + list(root.rglob("*.archive"))
    if archives:
        a = archives[0]
        return False, f"downloading {a.stat().st_size/1e9:.2f}G archive"
    versions = [p for p in root.iterdir() if p.is_dir()]
    bases = versions or [root]
    n = 0
    for base in bases:
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
                n += 1
    if n == 0:
        return False, "no videos yet"
    return True, f"{n} videos"


def both_ready() -> tuple[bool, list[str]]:
    msgs = []
    ok_all = True
    for owner, name in DATASETS:
        ok, msg = dataset_ready(owner, name)
        msgs.append(f"{owner}/{name}={msg}")
        ok_all = ok_all and ok
    return ok_all, msgs


def resolve_sources() -> list[Path]:
    sources: list[Path] = []
    for owner, name in DATASETS:
        root = CACHE_ROOT / owner / name
        versions = sorted(
            (p for p in root.iterdir() if p.is_dir() and p.name.isdigit()),
            key=lambda p: int(p.name),
        )
        sources.append(versions[-1] if versions else root)
    return sources


def resume_downloads_if_needed() -> None:
    """If the original download process died early, finish both via kagglehub."""
    ok, msgs = both_ready()
    if ok:
        return
    log("Download incomplete after worker exit — resuming with kagglehub for BOTH datasets")
    import kagglehub  # local import; only needed on resume path

    for slug in SLUGS:
        log(f"kagglehub.dataset_download({slug!r}) ...")
        path = kagglehub.dataset_download(slug)
        log(f"  done -> {path}")


def organize_and_upload() -> None:
    sources = resolve_sources()
    for src in sources:
        log(f"SOURCE {src}")
    cmd = [
        sys.executable,
        str(ORGANIZE),
        *[str(p) for p in sources],
        "--group-style",
        "L21",
    ]
    log("RUN " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    # Verify MinIO got objects
    mc = Path("/tmp/mc")
    if mc.exists():
        probe = subprocess.run(
            [str(mc), "ls", "myminio/videos/"],
            capture_output=True,
            text=True,
        )
        log("MinIO videos/ listing (head):")
        for line in (probe.stdout or probe.stderr or "").splitlines()[:40]:
            log("  " + line)
    log("SUCCESS both datasets organized + uploaded")


def main() -> int:
    log("Babysit started — requiring BOTH datasets before MinIO upload")
    log(f"Initial download PID hint={DOWNLOAD_PID_HINT} alive={pid_alive(DOWNLOAD_PID_HINT)}")

    # Phase 1: wait while original downloader runs
    while pid_alive(DOWNLOAD_PID_HINT):
        ok, msgs = both_ready()
        log("waiting download pid | " + " | ".join(msgs))
        if ok:
            break
        time.sleep(POLL_SEC)

    # Phase 2: ensure both complete (resume if needed)
    ok, msgs = both_ready()
    log("after download worker | " + " | ".join(msgs))
    if not ok:
        try:
            resume_downloads_if_needed()
        except Exception:
            log("RESUME FAILED:\n" + traceback.format_exc())
            return 1

    ok, msgs = both_ready()
    if not ok:
        log("ABORT still incomplete: " + " | ".join(msgs))
        return 1

    # Phase 3: organize + upload
    try:
        organize_and_upload()
    except Exception:
        log("UPLOAD FAILED:\n" + traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
