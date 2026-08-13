#!/usr/bin/env python3
"""Sequentially upload videos_grouped/*.mp4 to MinIO (avoids stuck parallel multipart)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

MC = "/tmp/mc"
SRC = Path("/Users/sunny/workspace/AI-Challenge-2026/data/videos_grouped")
DST = "myminio/videos"
LOG = Path("/tmp/minio-videos-sequential.log")
STATE = Path("/tmp/minio-videos-sequential.state")


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    STATE.write_text(line + "\n", encoding="utf-8")


def remote_exists(key: str, size: int) -> bool:
    r = subprocess.run([MC, "stat", f"{DST}/{key}"], capture_output=True, text=True)
    if r.returncode != 0:
        return False
    # parse "Size      : 80 MiB" roughly — accept if object exists
    return "Name" in (r.stdout or "")


def upload_one(path: Path) -> bool:
    key = f"{path.parent.name}/{path.name}"
    if remote_exists(key, path.stat().st_size):
        log(f"SKIP {key}")
        return True
    log(f"UPLOAD {key} ({path.stat().st_size / 1e6:.1f}MB)")
    r = subprocess.run(
        [MC, "cp", "--quiet", str(path), f"{DST}/{key}"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        log(f"FAIL {key}: {(r.stderr or r.stdout)[:300]}")
        return False
    log(f"OK {key}")
    return True


def main() -> int:
    files = sorted(SRC.glob("L*/**/*.mp4"))
    if not files:
        files = sorted(p for p in SRC.rglob("*.mp4") if p.is_file())
    log(f"START sequential upload n={len(files)}")
    ok = fail = skip = 0
    for i, path in enumerate(files, 1):
        key = f"{path.parent.name}/{path.name}"
        if remote_exists(key, path.stat().st_size):
            skip += 1
            if i % 25 == 0:
                log(f"progress {i}/{len(files)} ok={ok} skip={skip} fail={fail}")
            continue
        if upload_one(path):
            ok += 1
        else:
            fail += 1
            # retry once
            time.sleep(2)
            if upload_one(path):
                ok += 1
                fail -= 1
            else:
                log(f"GIVE_UP {key}")
        if i % 5 == 0:
            log(f"progress {i}/{len(files)} ok={ok} skip={skip} fail={fail}")
    log(f"DONE ok={ok} skip={skip} fail={fail} total={len(files)}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
