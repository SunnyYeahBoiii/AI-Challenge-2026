"""URL builders for keyframes and videos served from local disk."""

from pathlib import Path

from app.config import Config
from app.services.video_id import level_of, name_variants


def keyframe_url(video_id: str, frame_index: int) -> str:
    level = level_of(video_id)
    return f"/api/keyframes/{level}/{video_id}/{frame_index}.webp"


def video_url(video_id: str) -> str:
    """Return the local HLS playlist URL, falling back to a source video."""
    videos_dir = Path(Config.VIDEOS_DIR)
    for name in name_variants(video_id):
        if (videos_dir / name / "index.m3u8").is_file():
            return f"/api/media/videos/{name}/index.m3u8"
    for name in name_variants(video_id):
        for extension in ("mp4", "mov"):
            if (videos_dir / f"{name}.{extension}").is_file():
                return f"/api/media/videos/{name}.{extension}"
    return f"/api/media/videos/{video_id}/index.m3u8"
