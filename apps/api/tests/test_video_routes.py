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


@pytest.mark.parametrize(
    "path",
    [
        "/api/media/videos/missing.mp4",
        "/api/media/videos/invalid.name.mp4",
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
