"""URL builders for keyframes (local disk) and videos (CloudFront HLS).

Video read paths are plain CloudFront URL formatting. The browser fetches HLS
playlists and segments directly from CloudFront, so playback is not bottlenecked
by Flask's single-threaded proxy.

Keyframes are served from local disk via the /api/keyframes/... route (see
app.routes.keyframes) instead, since the full keyframe set lives on-machine.
"""

from app.config import Config


def keyframe_url(video_id: str, frame_index: int) -> str:
    level = video_id[:3]
    return f"/api/keyframes/{level}/{video_id}/{frame_index}.webp"


def video_url(video_id: str) -> str:
    """Public CloudFront HLS master-playlist URL."""
    level = video_id[:3]
    media_base_url = Config.MEDIA_BASE_URL.rstrip("/")
    return f"{media_base_url}/videos/{level}/{video_id}/index.m3u8"
