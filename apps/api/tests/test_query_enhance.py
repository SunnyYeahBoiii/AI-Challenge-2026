import json
from types import TracebackType
from urllib.error import URLError
from urllib.request import Request

import pytest

from app.config import Config
from app.services import query_enhance


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@pytest.fixture(autouse=True)
def clear_enhance_cache() -> None:
    query_enhance._enhance_cache.clear()


def test_enhance_query_uses_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "GEMINI_API_KEY", "secret")
    monkeypatch.setattr(Config, "GEMINI_MODEL", "gemini-test")
    calls: list[tuple[Request, float]] = []

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        calls.append((request, timeout))
        return FakeResponse(
            {"candidates": [{"content": {"parts": [{"text": "A person riding a bike."}]}}]}
        )

    monkeypatch.setattr(query_enhance, "urlopen", fake_urlopen)

    assert query_enhance.enhance_query("người đi xe đạp") == "A person riding a bike."
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url.endswith("/models/gemini-test:generateContent")
    assert request.get_header("X-goog-api-key") == "secret"
    assert timeout == Config.GEMINI_TIMEOUT


def test_enhance_query_reuses_successful_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "GEMINI_API_KEY", "secret")
    call_count = 0

    def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        nonlocal call_count
        call_count += 1
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "Enhanced"}]}}]})

    monkeypatch.setattr(query_enhance, "urlopen", fake_urlopen)

    assert query_enhance.enhance_query("query") == "Enhanced"
    assert query_enhance.enhance_query("query") == "Enhanced"
    assert call_count == 1


@pytest.mark.parametrize("api_key", ["", "   "])
def test_enhance_query_without_api_key_returns_raw_query(
    monkeypatch: pytest.MonkeyPatch, api_key: str
) -> None:
    monkeypatch.setattr(Config, "GEMINI_API_KEY", api_key)

    def fail_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        raise AssertionError("Gemini should not be called without an API key")

    monkeypatch.setattr(query_enhance, "urlopen", fail_urlopen)

    assert query_enhance.enhance_query("raw query") == "raw query"


def test_enhance_query_on_gemini_error_returns_raw_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "GEMINI_API_KEY", "secret")

    def fail_urlopen(request: Request, *, timeout: float) -> FakeResponse:
        raise URLError("offline")

    monkeypatch.setattr(query_enhance, "urlopen", fail_urlopen)

    assert query_enhance.enhance_query("raw query") == "raw query"
