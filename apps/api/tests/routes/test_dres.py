from __future__ import annotations

from typing import Any

from app.main import create_app
from app.routes import dres as routes
from app.services.dres import DRESError


def test_dres_login_route_validates_and_proxies(monkeypatch: Any) -> None:
    captured: list[tuple[str, str]] = []
    sdk: Any = routes

    def login(username: str, password: str) -> dict[str, str]:
        captured.append((username, password))
        return {"username": username}

    monkeypatch.setattr(
        sdk.dres_client,
        "login",
        login,
    )
    client = create_app().test_client()

    assert client.post("/api/dres/login", json={}).status_code == 400
    response = client.post(
        "/api/dres/login",
        json={"username": "team", "password": "secret"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"username": "team"}
    assert captured == [("team", "secret")]


def test_dres_routes_report_upstream_and_submission_errors(monkeypatch: Any) -> None:
    client = create_app().test_client()
    sdk: Any = routes
    monkeypatch.setattr(
        sdk.dres_client,
        "login",
        lambda *args: (_ for _ in ()).throw(DRESError("offline")),
    )
    assert client.post(
        "/api/dres/login",
        json={"username": "team", "password": "secret"},
    ).status_code == 502

    assert client.post("/api/dres/submit/kis", json={}).status_code == 400
    monkeypatch.setattr(
        sdk.dres_client,
        "submit",
        lambda *args, **kwargs: (_ for _ in ()).throw(DRESError("offline")),
    )
    response = client.post(
        "/api/dres/submit/kis",
        json={"frame_id": 30, "video_path": "V1", "timestamp": 1.0},
    )
    assert response.status_code == 502


def test_dres_submit_route_forwards_validated_fields(monkeypatch: Any) -> None:
    captured: dict[str, object] = {}
    sdk: Any = routes

    def submit(submission_type: str, **kwargs: object) -> dict[str, object]:
        captured.update({"submission_type": submission_type, **kwargs})
        return {"status": True}

    monkeypatch.setattr(sdk.dres_client, "submit", submit)
    response = create_app().test_client().post(
        "/api/dres/submit/qa",
        json={
            "frame_id": 30,
            "video_path": "V1",
            "timestamp": 1.5,
            "answer": "two",
        },
    )

    assert response.status_code == 200
    assert captured == {
        "submission_type": "qa",
        "video_id": "V1",
        "timestamp": 1.5,
        "answer": "two",
    }
