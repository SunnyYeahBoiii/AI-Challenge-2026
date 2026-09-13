"""Unit tests for local media URL helpers."""

from app.services.storage import keyframe_url, video_url


def test_video_url_is_local_mp4_route() -> None:
    assert video_url("L26_V211") == "/api/media/videos/L26_V211.mp4"


def test_keyframe_url_is_local_api_route() -> None:
    assert keyframe_url("L26_V211", 42) == "/api/keyframes/L26/L26_V211/42.webp"
