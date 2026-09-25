from pathlib import Path

import pytest
from flask import Flask

from app.routes.video_stream import video_stream_bp
from app.services import local_videos


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    (tmp_path / "N001").mkdir()
    (tmp_path / "N001" / "N001_V001.mov").write_bytes(bytes(range(256)) * 4)
    monkeypatch.setattr("app.services.local_videos.Config.VIDEOS_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.local_videos.Config.VIDEOS_FASTSTART_DIR", str(tmp_path / "none"))
    monkeypatch.setattr(local_videos, "_index", {})
    app = Flask(__name__)
    app.register_blueprint(video_stream_bp)
    return app.test_client()


def test_range_request_returns_206_slice(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/videos/N001_V001/stream", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.data == bytes(range(10, 20))
    assert r.headers["Content-Range"] == "bytes 10-19/1024"
    assert r.headers["Accept-Ranges"] == "bytes"


def test_full_request_is_200_mp4(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/videos/N001_V001/stream")
    assert r.status_code == 200
    assert r.mimetype == "video/mp4"


def test_unknown_video_404(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/videos/../etc/stream").status_code == 404
    assert client.get("/api/videos/X999_V001/stream").status_code == 404


def test_hls_playlist_and_segment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = tmp_path / "S01" / "S01-V001"
    d.mkdir(parents=True)
    (d / "index.m3u8").write_text("#EXTM3U\n")
    (d / "seg00001.m4s").write_bytes(b"x" * 100)
    monkeypatch.setattr("app.services.local_videos.Config.VIDEOS_DIR", str(tmp_path / "none"))
    monkeypatch.setattr("app.services.local_videos.Config.VIDEOS_FASTSTART_DIR", str(tmp_path / "none"))
    monkeypatch.setattr("app.services.local_videos.Config.VIDEOS_HLS_DIR", str(tmp_path))
    monkeypatch.setattr(local_videos, "_index", {})
    monkeypatch.setattr(local_videos, "_hls_index", {})
    app = Flask(__name__)
    app.register_blueprint(video_stream_bp)
    c = app.test_client()
    r = c.get("/api/videos/S01-V001/hls/index.m3u8")
    assert r.status_code == 200 and r.mimetype == "application/vnd.apple.mpegurl"
    r = c.get("/api/videos/S01-V001/hls/seg00001.m4s", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and "immutable" in r.headers["Cache-Control"]
    assert c.get("/api/videos/S01-V001/hls/../x.m3u8").status_code == 404
    assert c.get("/api/videos/S01-V001/hls/evil.txt").status_code == 404
