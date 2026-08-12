"""Public URL builders for keyframes/videos hosted on MinIO (path-style S3 addressing).

Read paths never touch the MinIO SDK — they're plain string formatting so a
request never pays for a client/auth round trip just to build a URL for an
already-public bucket. The SDK is only needed by upload scripts (see
scripts/upload_to_minio.py).
"""

from app.config import Config


def _base_url() -> str:
    scheme = "https" if Config.MINIO_SECURE else "http"
    return f"{scheme}://{Config.MINIO_ENDPOINT}"


def keyframe_url(video_id: str, frame_index: int) -> str:
    level = video_id[:3]
    return f"{_base_url()}/{Config.MINIO_BUCKET_KEYFRAMES}/{level}/{video_id}/{frame_index}.webp"


def video_url(video_id: str) -> str:
    level = video_id[:3]
    return f"{_base_url()}/{Config.MINIO_BUCKET_VIDEOS}/{level}/{video_id}.mp4"
