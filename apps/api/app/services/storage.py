"""Public URL builders for keyframes/videos hosted on MinIO (path-style S3 addressing).

Read paths never touch the MinIO SDK — plain string formatting only. The browser
talks to MinIO/Cloudflare directly (Range/206 + CORS already work there), so
playback is not bottlenecked by Flask's single-threaded proxy.
"""

from app.config import Config


def _base_url() -> str:
    scheme = "https" if Config.MINIO_SECURE else "http"
    return f"{scheme}://{Config.MINIO_ENDPOINT}"


def keyframe_url(video_id: str, frame_index: int) -> str:
    level = video_id[:3]
    return f"{_base_url()}/{Config.MINIO_BUCKET_KEYFRAMES}/{level}/{video_id}/{frame_index}.webp"


def video_url(video_id: str) -> str:
    """Public MinIO HLS playlist URL — video.js/VHS fetches segments via XHR."""
    level = video_id[:3]
    return f"{_base_url()}/{Config.MINIO_BUCKET_VIDEOS}/{level}/{video_id}/index.m3u8"
