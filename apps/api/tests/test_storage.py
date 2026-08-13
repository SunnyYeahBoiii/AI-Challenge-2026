"""Unit tests for MinIO storage URL helpers."""

import pytest

from app.services.storage import video_url


def test_video_url_is_public_minio_hls_playlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.storage.Config.MINIO_ENDPOINT", "s3.example.test")
    monkeypatch.setattr("app.services.storage.Config.MINIO_SECURE", True)
    monkeypatch.setattr("app.services.storage.Config.MINIO_BUCKET_VIDEOS", "videos")
    assert video_url("L26_V211") == "https://s3.example.test/videos/L26/L26_V211/index.m3u8"
