from pathlib import Path

import pytest
from flask.testing import FlaskClient

from app.config import Config
from app.main import create_app


@pytest.fixture
def client() -> FlaskClient:
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_local_video_supports_byte_ranges(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "L21_V001.mp4").write_bytes(b"0123456789")
    monkeypatch.setattr(Config, "VIDEOS_DIR", str(tmp_path))

    response = client.get(
        "/api/media/videos/L21_V001.mp4",
        headers={"Range": "bytes=2-5"},
    )

    assert response.status_code == 206
    assert response.data == b"2345"
    assert response.headers["Content-Range"] == "bytes 2-5/10"
    assert response.mimetype == "video/mp4"


def test_local_hls_assets_are_served(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    video_dir = tmp_path / "L21_V001"
    video_dir.mkdir()
    (video_dir / "index.m3u8").write_text(
        "#EXTM3U\n#EXT-X-MAP:URI=\"init.mp4\"\n#EXTINF:6.0,\nseg00000.m4s\n"
    )
    (video_dir / "init.mp4").write_bytes(b"init")
    (video_dir / "seg00000.m4s").write_bytes(b"0123456789")
    monkeypatch.setattr(Config, "VIDEOS_DIR", str(tmp_path))

    playlist = client.get("/api/media/videos/L21_V001/index.m3u8")
    segment = client.get(
        "/api/media/videos/L21_V001/seg00000.m4s",
        headers={"Range": "bytes=2-5"},
    )

    assert playlist.status_code == 200
    assert playlist.mimetype == "application/vnd.apple.mpegurl"
    assert segment.status_code == 206
    assert segment.data == b"2345"
    assert segment.mimetype == "video/iso.segment"


def test_local_mov_source_is_served(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "N011_V001.mov").write_bytes(b"video")
    monkeypatch.setattr(Config, "VIDEOS_DIR", str(tmp_path))

    response = client.get("/api/media/videos/N011_V001.mov")

    assert response.status_code == 200
    assert response.data == b"video"
    assert response.mimetype == "video/quicktime"


@pytest.mark.parametrize(
    "path",
    [
        "/api/media/videos/missing.mp4",
        "/api/media/videos/invalid.name.mp4",
        "/api/media/videos/L21_V001/not-a-segment.txt",
        "/api/media/videos/invalid.name/index.m3u8",
    ],
)
def test_local_video_rejects_missing_or_invalid_names(
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
) -> None:
    monkeypatch.setattr(Config, "VIDEOS_DIR", str(tmp_path))

    assert client.get(path).status_code == 404
