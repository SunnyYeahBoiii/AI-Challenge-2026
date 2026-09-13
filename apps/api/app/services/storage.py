"""URL builders for keyframes and videos served from local disk."""


def keyframe_url(video_id: str, frame_index: int) -> str:
    level = video_id[:3]
    return f"/api/keyframes/{level}/{video_id}/{frame_index}.webp"


def video_url(video_id: str) -> str:
    """Return the same-origin API URL for a local MP4 file."""
    return f"/api/media/videos/{video_id}.mp4"
