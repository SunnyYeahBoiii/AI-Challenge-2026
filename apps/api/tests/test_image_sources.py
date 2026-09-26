"""Remote image input tests."""

from io import BytesIO
import socket
from urllib.request import Request

from PIL import Image
import pytest
from flask.testing import FlaskClient

from app.main import create_app
from app.services import image_sources
from app.services.image_sources import ImageSourceError, fetch_public_image


@pytest.fixture
def client() -> FlaskClient:
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color="red").save(output, format="PNG")
    return output.getvalue()


class FakeResponse:
    def __init__(self, data: bytes, content_length: int | None = None) -> None:
        self._data = data
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._data if size < 0 else self._data[:size]


def test_validate_public_url_rejects_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))],
    )

    with pytest.raises(ImageSourceError, match="public internet host"):
        image_sources.validate_public_image_url("http://example.test/image.png")


def test_redirect_handler_revalidates_private_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))],
    )
    handler = image_sources._PublicImageRedirectHandler()

    with pytest.raises(ImageSourceError, match="public internet host"):
        handler.redirect_request(
            Request("https://example.test/image.png"),
            None,
            302,
            "Found",
            {},
            "http://127.0.0.1/private.png",
        )


def test_fetch_public_image_returns_valid_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(image_sources, "validate_public_image_url", lambda url: None)
    monkeypatch.setattr(image_sources, "_open_image_url", lambda url: FakeResponse(_png_bytes()))

    image = fetch_public_image("https://example.test/image.png")

    assert image.data == _png_bytes()
    assert image.media_type == "image/png"


def test_fetch_public_image_rejects_oversized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(image_sources, "validate_public_image_url", lambda url: None)
    monkeypatch.setattr(
        image_sources,
        "_open_image_url",
        lambda url: FakeResponse(b"", image_sources.MAX_IMAGE_BYTES + 1),
    )

    with pytest.raises(ImageSourceError, match="8 MiB"):
        fetch_public_image("https://example.test/large.png")


def test_fetch_public_image_rejects_non_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(image_sources, "validate_public_image_url", lambda url: None)
    monkeypatch.setattr(
        image_sources,
        "_open_image_url",
        lambda url: FakeResponse(b"not an image"),
    )

    with pytest.raises(ImageSourceError, match="valid raster image"):
        fetch_public_image("https://example.test/not-image")


def test_fetch_public_image_reports_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_open(_url: str) -> FakeResponse:
        raise TimeoutError

    monkeypatch.setattr(image_sources, "validate_public_image_url", lambda url: None)
    monkeypatch.setattr(image_sources, "_open_image_url", fail_open)

    with pytest.raises(ImageSourceError, match="Could not download") as error:
        fetch_public_image("https://example.test/image.png")

    assert error.value.status_code == 502


def test_fetch_image_route_returns_data_url(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.routes import images

    monkeypatch.setattr(
        images,
        "fetch_public_image",
        lambda url: image_sources.RemoteImage(_png_bytes(), "image/png"),
    )

    response = client.post("/api/images/fetch", json={"url": "https://example.test/image.png"})

    assert response.status_code == 200
    assert response.json["data"]["data_url"].startswith("data:image/png;base64,")
    assert response.json["data"]["media_type"] == "image/png"
    assert response.json["data"]["size"] == len(_png_bytes())


def test_fetch_image_route_rejects_missing_url(client: FlaskClient) -> None:
    response = client.post("/api/images/fetch", json={})

    assert response.status_code == 400
    assert response.json["error"]["code"] == "VALIDATION_ERROR"
