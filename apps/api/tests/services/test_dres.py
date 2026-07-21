from __future__ import annotations

import io
import json
from email.message import Message
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from app.services import dres as module
from app.services.dres import DRESClient, DRESError


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_login_and_submit_use_dres_v2_without_leaking_session(monkeypatch: Any) -> None:
    responses = [
        FakeResponse({"id": "u1", "username": "team", "sessionId": "secret token"}),
        FakeResponse({"status": True, "description": "accepted"}),
    ]
    calls: list[tuple[Request, float]] = []

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        calls.append((request, timeout))
        return responses.pop(0)

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    client = DRESClient("https://dres.example/", "eval/id", timeout_seconds=3.0)

    login = client.login("team", "password")
    result = client.submit(
        "qa",
        video_id="L01_V001",
        timestamp=1.2346,
        answer="  two people  ",
    )

    assert login == {"id": "u1", "username": "team"}
    assert result["status"] is True
    assert calls[0][0].full_url == "https://dres.example/api/v2/login"
    login_data = calls[0][0].data
    assert isinstance(login_data, bytes)
    assert json.loads(login_data) == {
        "username": "team",
        "password": "password",
    }
    assert calls[1][0].full_url.endswith(
        "/api/v2/submit/eval%2Fid?session=secret+token"
    )
    submit_data = calls[1][0].data
    assert isinstance(submit_data, bytes)
    answer = json.loads(submit_data)["answerSets"][0]["answers"][0]
    assert answer == {
        "mediaItemName": "L01_V001",
        "start": 1235,
        "end": 1235,
        "text": "two people",
    }
    assert calls[1][1] == 3.0


def test_client_validates_configuration_login_and_submission(monkeypatch: Any) -> None:
    with pytest.raises(DRESError, match="BASE_URL"):
        DRESClient("", "evaluation").login("user", "password")
    with pytest.raises(DRESError, match="HTTP"):
        DRESClient("not-a-url", "evaluation").login("user", "password")
    with pytest.raises(DRESError, match="TIMEOUT"):
        DRESClient("https://dres", "evaluation", timeout_seconds=float("nan")).login(
            "user", "password"
        )

    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: FakeResponse({"id": "u"}))
    with pytest.raises(DRESError, match="sessionId"):
        DRESClient("https://dres", "evaluation").login("user", "password")

    client = DRESClient("https://dres", "", session_token="token")
    with pytest.raises(DRESError, match="EVALUATION_ID"):
        client.submit("kis", video_id="V1", timestamp=0.0)

    client = DRESClient("https://dres", "evaluation")
    with pytest.raises(DRESError, match="not logged in"):
        client.submit("kis", video_id="V1", timestamp=0.0)

    authenticated = DRESClient(
        "https://dres",
        "evaluation",
        session_token="token",
    )
    with pytest.raises(ValueError, match="submission type"):
        authenticated.submit("unknown", video_id="V1", timestamp=0.0)
    with pytest.raises(ValueError, match="timestamp"):
        authenticated.submit("kis", video_id="V1", timestamp=float("inf"))
    with pytest.raises(ValueError, match="answer"):
        authenticated.submit("qa", video_id="V1", timestamp=0.0)


@pytest.mark.parametrize(
    "error",
    [
        HTTPError(
            "https://dres",
            401,
            "Unauthorized",
            Message(),
            io.BytesIO(b'{"description":"bad credentials"}'),
        ),
        URLError("offline"),
    ],
)
def test_client_wraps_http_and_network_failures(monkeypatch: Any, error: Exception) -> None:
    def fail(*args: object, **kwargs: object) -> FakeResponse:
        raise error

    monkeypatch.setattr(module, "urlopen", fail)

    with pytest.raises(DRESError):
        DRESClient("https://dres", "evaluation").login("user", "password")


@pytest.mark.parametrize("payload", [b"not-json", b"[]"])
def test_client_rejects_invalid_responses(monkeypatch: Any, payload: bytes) -> None:
    response = FakeResponse({})
    response.payload = payload
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: response)

    with pytest.raises(DRESError, match="JSON"):
        DRESClient("https://dres", "evaluation").login("user", "password")
