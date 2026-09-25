"""Locate local mp4/mov files by video_id.

Layout on disk is <VIDEOS_DIR>/<group>/<video_id>.{mp4,mov}. Files are indexed once
(a few hundred stat-free directory listings) and re-scanned on a miss, so newly
copied videos show up without a restart. Lookup goes through the dict, never through
a path built from user input, so there is no traversal surface.
"""

import threading
import time
from pathlib import Path

from app.config import Config

_EXTENSIONS = {".mp4", ".mov"}
_RESCAN_COOLDOWN_S = 5.0

_lock = threading.Lock()
_index: dict[str, Path] = {}
_hls_index: dict[str, Path] = {}
_last_scan = 0.0


def _scan(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not root.is_dir():
        return found
    for group in root.iterdir():
        if not group.is_dir():
            continue
        for f in group.iterdir():
            if f.suffix.lower() in _EXTENSIONS and not f.name.startswith("."):
                found[f.stem] = f
    return found


def _scan_hls(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not root.is_dir():
        return found
    for group in root.iterdir():
        if not group.is_dir():
            continue
        for d in group.iterdir():
            if not d.name.startswith(".") and (d / "index.m3u8").is_file():
                found[d.name] = d
    return found


def _refresh() -> None:
    global _index, _hls_index, _last_scan
    merged = _scan(Path(Config.VIDEOS_DIR))
    # Faststart copies (moov first) win: browser can start playing without a tail seek.
    merged.update(_scan(Path(Config.VIDEOS_FASTSTART_DIR)))
    _index = merged
    _hls_index = _scan_hls(Path(Config.VIDEOS_HLS_DIR))
    _last_scan = time.monotonic()


def resolve_video_path(video_id: str) -> Path | None:
    with _lock:
        if not _index:
            _refresh()
        path = _index.get(video_id)
        if path is None and time.monotonic() - _last_scan > _RESCAN_COOLDOWN_S:
            _refresh()
            path = _index.get(video_id)
        return path


def resolve_hls_dir(video_id: str) -> Path | None:
    """Directory holding index.m3u8 + segments for video_id, or None if not packaged."""
    with _lock:
        if not _index and not _hls_index:
            _refresh()
        return _hls_index.get(video_id)


def has_hls(video_id: str) -> bool:
    return resolve_hls_dir(video_id) is not None
