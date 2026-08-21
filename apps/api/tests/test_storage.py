"""Unit tests for keyframe (local disk) and CloudFront video URL helpers."""

import pytest

from app.services.storage import keyframe_url, video_url


def test_video_url_is_cloudfront_hls_master_playlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.storage.Config.MEDIA_BASE_URL", "https://cdn.example.test/")
    assert video_url("L26_V211") == "https://cdn.example.test/videos/L26/L26_V211/index.m3u8"


def test_keyframe_url_is_local_api_route() -> None:
    assert keyframe_url("L26_V211", 42) == "/api/keyframes/L26/L26_V211/42.webp"
