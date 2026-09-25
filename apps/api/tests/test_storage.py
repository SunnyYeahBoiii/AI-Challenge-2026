"""Unit tests for keyframe (local disk) and video (MinIO) URL helpers."""

import pytest

from app.services.storage import keyframe_url, video_url


def test_video_url_local_is_range_stream_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.storage.Config.VIDEO_SOURCE", "local")
    monkeypatch.setattr("app.services.storage.Config.VIDEO_PUBLIC_BASE", "")
    monkeypatch.setattr("app.services.storage.has_hls", lambda _v: False)
    assert video_url("N001_V001") == "/api/videos/N001_V001/stream"
    monkeypatch.setattr("app.services.storage.Config.VIDEO_PUBLIC_BASE", "http://h:5001")
    assert video_url("N001_V001") == "http://h:5001/api/videos/N001_V001/stream"


def test_video_url_is_public_minio_hls_playlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.storage.Config.VIDEO_SOURCE", "minio")
    monkeypatch.setattr("app.services.storage.Config.MINIO_ENDPOINT", "s3.example.test")
    monkeypatch.setattr("app.services.storage.Config.MINIO_SECURE", True)
    monkeypatch.setattr("app.services.storage.Config.MINIO_BUCKET_VIDEOS", "videos")
    assert video_url("L26_V211") == "https://s3.example.test/videos/L26/L26_V211/index.m3u8"


def test_keyframe_url_is_local_api_route() -> None:
    assert keyframe_url("L26_V211", 42) == "/api/keyframes/L26/L26_V211/42.webp"
    assert keyframe_url("M01_V015", 7) == "/api/keyframes/M01/M01_V015/7.webp"
    assert keyframe_url("N066-V002", 25) == "/api/keyframes/N066/N066-V002/25.webp"


def test_video_url_prefers_local_hls_when_packaged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.storage.Config.VIDEO_SOURCE", "local")
    monkeypatch.setattr("app.services.storage.Config.VIDEO_PUBLIC_BASE", "")
    monkeypatch.setattr("app.services.storage.has_hls", lambda v: v == "S01-V001")
    assert video_url("S01-V001") == "/api/videos/S01-V001/hls/index.m3u8"
    assert video_url("N001_V001") == "/api/videos/N001_V001/stream"
