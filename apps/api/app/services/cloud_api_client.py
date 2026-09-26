"""Minimal REST client for cloud-api (shared TRAKE board)."""
import json
import urllib.error
import urllib.request
from typing import Any

from app.config import Config


class CloudApiError(Exception):
    pass


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{Config.CLOUD_API_URL.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="ignore")
        raise CloudApiError(f"cloud-api {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise CloudApiError(f"cloud-api unreachable: {error.reason}") from error


def get_board() -> dict[str, Any]:
    return _request("GET", "/boards/shared")


def add_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", "/boards/shared/candidates", payload)
