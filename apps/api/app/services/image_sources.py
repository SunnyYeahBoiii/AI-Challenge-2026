"""Load and validate public image URLs for image-query input."""

from dataclasses import dataclass
from http.client import HTTPResponse
from io import BytesIO
import ipaddress
import socket
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_FETCH_TIMEOUT_SECONDS = 5.0
MAX_IMAGE_REDIRECTS = 3


class ImageSourceError(Exception):
    """A user-facing image source validation or fetch failure."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class RemoteImage:
    """Validated remote image bytes and their detected media type."""

    data: bytes
    media_type: str


def validate_public_image_url(url: str) -> None:
    """Reject malformed URLs and hosts that resolve outside the public internet."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ImageSourceError("INVALID_IMAGE_URL", "Image URL is invalid", 400) from exc

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ImageSourceError(
            "INVALID_IMAGE_URL",
            "Image URL must use http or https",
            400,
        )
    if parsed.username is not None or parsed.password is not None:
        raise ImageSourceError(
            "INVALID_IMAGE_URL",
            "Image URL must not contain credentials",
            400,
        )

    lookup_port = port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            lookup_port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ImageSourceError(
            "IMAGE_FETCH_FAILED",
            "Could not resolve the image host",
            502,
        ) from exc

    for address in addresses:
        host = str(address[4][0]).split("%", maxsplit=1)[0]
        if not ipaddress.ip_address(host).is_global:
            raise ImageSourceError(
                "INVALID_IMAGE_URL",
                "Image URL must point to a public internet host",
                400,
            )


class _PublicImageRedirectHandler(HTTPRedirectHandler):
    max_redirections = MAX_IMAGE_REDIRECTS
    max_repeats = MAX_IMAGE_REDIRECTS

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        safe_url = urljoin(req.full_url, newurl)
        validate_public_image_url(safe_url)
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


def _open_image_url(url: str) -> HTTPResponse:
    opener = build_opener(_PublicImageRedirectHandler())
    request = Request(
        url,
        headers={
            "Accept": "image/*",
            "User-Agent": "FrameSeeker/1.0",
        },
    )
    return cast(HTTPResponse, opener.open(request, timeout=IMAGE_FETCH_TIMEOUT_SECONDS))


def _detect_media_type(data: bytes) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise ImageSourceError(
            "INVALID_IMAGE",
            "URL did not return a valid raster image",
            400,
        ) from exc

    media_type = Image.MIME.get(image_format or "")
    if not media_type:
        raise ImageSourceError(
            "INVALID_IMAGE",
            "Image format is not supported",
            400,
        )
    return media_type


def fetch_public_image(url: str) -> RemoteImage:
    """Fetch one public image with redirect, timeout, and size protections."""
    validate_public_image_url(url)
    try:
        with _open_image_url(url) as response:
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > MAX_IMAGE_BYTES:
                        raise ImageSourceError(
                            "IMAGE_TOO_LARGE",
                            "Image must be 8 MiB or smaller",
                            400,
                        )
                except ValueError:
                    pass
            data = response.read(MAX_IMAGE_BYTES + 1)
    except ImageSourceError:
        raise
    except HTTPError as exc:
        raise ImageSourceError(
            "IMAGE_FETCH_FAILED",
            f"Image server returned HTTP {exc.code}",
            502,
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise ImageSourceError(
            "IMAGE_FETCH_FAILED",
            "Could not download the image URL",
            502,
        ) from exc

    if len(data) > MAX_IMAGE_BYTES:
        raise ImageSourceError(
            "IMAGE_TOO_LARGE",
            "Image must be 8 MiB or smaller",
            400,
        )

    return RemoteImage(data=data, media_type=_detect_media_type(data))
