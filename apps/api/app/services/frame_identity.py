from __future__ import annotations

from collections.abc import Mapping


def build_frame_uid(video_id: str, frame_index: int) -> str:
    """Build a stable cross-model identifier for one Frame."""
    normalized_video_id = video_id.strip()
    if not normalized_video_id:
        raise ValueError("video_id is required to build frame_uid")
    if frame_index < 0:
        raise ValueError("frame_index must be non-negative")
    return f"{normalized_video_id}:{frame_index:08d}"


def frame_uid(frame: Mapping[str, object]) -> str:
    """Return a stable Frame identity without relying on a database primary key."""
    existing = str(frame.get("frame_uid", "")).strip()
    if existing:
        return existing

    frame_path = str(frame.get("frame_path", "")).strip().replace("\\", "/")
    if frame_path:
        return frame_path

    video_id = str(frame.get("video_id", "")).strip()
    raw_frame_index = frame.get("frame_index", frame.get("frame_idx", 0))
    if not isinstance(raw_frame_index, (str, int, float)):
        raise ValueError("frame_index must be numeric")
    return build_frame_uid(video_id, int(raw_frame_index or 0))
