"""Unit tests for local media URL helpers."""

from pathlib import Path

import pytest

from app.config import Config
from app.services.storage import keyframe_url, video_url


def test_video_url_prefers_local_hls_playlist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    video_dir = tmp_path / "L26_V211"
    video_dir.mkdir()
    (video_dir / "index.m3u8").write_text("#EXTM3U\n")
    monkeypatch.setattr(Config, "VIDEOS_DIR", str(tmp_path))

    assert video_url("L26_V211") == "/api/media/videos/L26_V211/index.m3u8"


def test_video_url_resolves_underscore_dir_for_dash_video_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """N series: index and keyframes use ``N001-V001``, videos ship ``N001_V001``."""
    (tmp_path / "N001_V001").mkdir()
    (tmp_path / "N001_V001" / "index.m3u8").write_text("#EXTM3U\n")
    monkeypatch.setattr(Config, "VIDEOS_DIR", str(tmp_path))

    assert video_url("N001-V001") == "/api/media/videos/N001_V001/index.m3u8"


@pytest.mark.parametrize("extension", ["mp4", "mov"])
def test_video_url_falls_back_to_local_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extension: str
) -> None:
    (tmp_path / f"L26_V211.{extension}").write_bytes(b"video")
    monkeypatch.setattr(Config, "VIDEOS_DIR", str(tmp_path))

    assert video_url("L26_V211") == f"/api/media/videos/L26_V211.{extension}"


def test_video_url_prefers_hls_over_source_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "M01_V001").mkdir()
    (tmp_path / "M01_V001" / "index.m3u8").write_text("#EXTM3U\n")
    (tmp_path / "M01_V001.mp4").write_bytes(b"video")
    monkeypatch.setattr(Config, "VIDEOS_DIR", str(tmp_path))

    assert video_url("M01_V001") == "/api/media/videos/M01_V001/index.m3u8"


@pytest.mark.parametrize(
    ("video_id", "frame_index", "expected"),
    [
        ("L26_V211", 42, "/api/keyframes/L26/L26_V211/42.webp"),
        ("M01_V001", 383, "/api/keyframes/M01/M01_V001/383.webp"),
        ("S01-V001", 33, "/api/keyframes/S01/S01-V001/33.webp"),
        ("N001-V001", 0, "/api/keyframes/N001/N001-V001/0.webp"),
        ("N100-V012", 0, "/api/keyframes/N100/N100-V012/0.webp"),
    ],
)
def test_keyframe_url_uses_full_level(
    video_id: str, frame_index: int, expected: str
) -> None:
    assert keyframe_url(video_id, frame_index) == expected
