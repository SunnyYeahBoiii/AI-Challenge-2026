"""URL builders for keyframes (local disk) and videos (local Range stream or MinIO).

Video_source=local (default) serves mp4/mov from disk via app.routes.video_stream.
Video_source=minio: read paths never touch the MinIO SDK — plain string formatting only. The
browser talks to MinIO/Cloudflare directly (Range/206 + CORS already work
there), so playback is not bottlenecked by Flask's single-threaded proxy.

Keyframes are served from local disk via the /api/keyframes/... route (see
app.routes.keyframes) instead, since the full keyframe set lives on-machine.
"""

from app.config import Config
from app.services.local_videos import has_hls


def _base_url() -> str:
    scheme = "https" if Config.MINIO_SECURE else "http"
    return f"{scheme}://{Config.MINIO_ENDPOINT}"


def _level(video_id: str) -> str:
    # L21_V001 -> L21, M01_V001 -> M01, N066-V002 -> N066 ([:3] breaks N).
    return video_id.split("_")[0].split("-")[0]


def keyframe_url(video_id: str, frame_index: int) -> str:
    level = _level(video_id)
    return f"/api/keyframes/{level}/{video_id}/{frame_index}.webp"


def video_url(video_id: str) -> str:
    """Local Range-stream URL, or public MinIO HLS playlist when VIDEO_SOURCE=minio."""
    if Config.VIDEO_SOURCE == "local":
        if has_hls(video_id):
            return f"{Config.VIDEO_PUBLIC_BASE}/api/videos/{video_id}/hls/index.m3u8"
        return f"{Config.VIDEO_PUBLIC_BASE}/api/videos/{video_id}/stream"
    level = _level(video_id)
    return f"{_base_url()}/{Config.MINIO_BUCKET_VIDEOS}/{level}/{video_id}/index.m3u8"
