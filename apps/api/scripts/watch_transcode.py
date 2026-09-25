"""Live progress for transcode_heavy_videos.py + package_hls.py (read-only, safe to run anytime).

    python3 apps/api/scripts/watch_transcode.py --group S01

Expected output size = duration x 1.85Mbps (bitrate of the test encode), so per-file % is
approximate; ETA uses the aggregate write rate over the last ~90s.
"""

import argparse
import subprocess
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "data"
EST_BPS = 1.85e6


def duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def fmt(sec: float) -> str:
    h, m = divmod(int(sec) // 60, 60)
    return f"{h}h{m:02d}m"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="S01")
    ap.add_argument("--interval", type=float, default=5)
    a = ap.parse_args()
    src_dir, fs_dir, hls_dir = ROOT / "videos_grouped" / a.group, ROOT / "videos_faststart" / a.group, ROOT / "videos_hls" / a.group
    srcs = sorted(f for f in src_dir.iterdir() if f.suffix.lower() in {".mp4", ".mov"} and not f.name.startswith("."))
    dur = {f.stem: duration(f) for f in srcs}
    expect = {k: v * EST_BPS / 8 for k, v in dur.items()}
    hist: deque[tuple[float, float]] = deque(maxlen=20)
    while True:
        rows, done_b, total_b, ndone, nhls = [], 0.0, sum(expect.values()), 0, 0
        for f in srcs:
            k = f.stem
            final, part = fs_dir / f"{k}.mp4", fs_dir / f".{k}.mp4.part"
            hls = (hls_dir / k / "index.m3u8").exists()
            nhls += hls
            if final.exists() and final.stat().st_size > 0:
                sz, state = final.stat().st_size, "HLS " if hls else "mp4 "
                pct, ndone = 100.0, ndone + 1
            elif part.exists():
                sz = part.stat().st_size
                pct, state = min(99.0, 100 * sz / expect[k]), "RUN "
            else:
                sz, pct, state = 0, 0.0, "wait"
            done_b += min(sz, expect[k]) if state != "wait" else 0
            bar = "#" * int(pct / 5) + "." * (20 - int(pct / 5))
            rows.append(f"  {k:<10} {state} [{bar}] {pct:5.1f}%  {sz / 1e9:5.2f}GB  {fmt(dur[k])}")
        now = time.time()
        hist.append((now, done_b))
        eta = "…"
        if len(hist) > 3 and hist[-1][1] > hist[0][1]:
            rate = (hist[-1][1] - hist[0][1]) / (hist[-1][0] - hist[0][0])
            eta = f"{rate / 1e6:.1f}MB/s · ETA {fmt((total_b - done_b) / rate)} ({time.strftime('%H:%M', time.localtime(now + (total_b - done_b) / rate))})"
        n_ff = subprocess.run("pgrep -f '^ffmpeg .*-c:v h264_videotoolbox' | wc -l", shell=True, capture_output=True, text=True).stdout.strip()
        print("\033[2J\033[H" + f"{a.group}  {time.strftime('%H:%M:%S')}  ffmpeg encode: {n_ff}  mp4 xong {ndone}/{len(srcs)}  HLS xong {nhls}/{len(srcs)}")
        print(f"  tổng {done_b / total_b * 100:.1f}%  {eta}\n" + "\n".join(rows) + "\n  (Ctrl+C để thoát)", flush=True)
        time.sleep(a.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
