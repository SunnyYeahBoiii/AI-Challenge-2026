#!/usr/bin/env python3
"""Upload one video to MinIO and print progress; then restart full mirror if OK."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

MC = "/tmp/mc"
SRC = Path("/Users/sunny/workspace/AI-Challenge-2026/data/videos_grouped/L21/L21_V005.mp4")
DST = "myminio/videos/L21/L21_V005.mp4"
GROUPED = Path("/Users/sunny/workspace/AI-Challenge-2026/data/videos_grouped")
LOG = Path("/tmp/minio-videos-upload.log")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def main() -> int:
    print(f"src_size_mb={SRC.stat().st_size / 1e6:.1f}")
    log = open("/tmp/mc-one-video.log", "w")
    proc = subprocess.Popen(
        [MC, "cp", str(SRC), DST],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    t0 = time.time()
    while proc.poll() is None:
        time.sleep(15)
        inc = run([MC, "ls", "--incomplete", "myminio/videos/L21/"])
        print(
            f"elapsed={time.time() - t0:.0f}s "
            f"incomplete={(inc.stdout or '').strip()[:160]!r}"
        )
        if time.time() - t0 > 900:
            proc.kill()
            print("TIMEOUT")
            break
    print("exit", proc.poll())
    stat = run([MC, "stat", DST])
    print(stat.stdout or stat.stderr)
    if proc.poll() != 0:
        return 1

    # Restart full mirror (low concurrency)
    subprocess.run(["pkill", "-f", "mc mirror.*videos_grouped"], capture_output=True)
    time.sleep(1)
    fout = open(LOG, "a")
    mirror = subprocess.Popen(
        [
            "env",
            "MC_UPLOAD_CONCURRENCY=2",
            MC,
            "mirror",
            "--overwrite",
            "--exclude",
            ".DS_Store",
            f"{GROUPED}/",
            "myminio/videos/",
        ],
        stdin=subprocess.DEVNULL,
        stdout=fout,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    Path("/tmp/minio-videos-upload.pid").write_text(str(mirror.pid) + "\n")
    print("mirror_started", mirror.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
