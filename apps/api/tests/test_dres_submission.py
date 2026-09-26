"""DRES KIS/QA submission contract tests."""

import pytest
from flask import Flask

from app.routes.dres import dres_bp, verdict_code
from app.services.dres_client import DresClient, DresError


def test_submit_qa_builds_dres_text_contract(monkeypatch) -> None:
    client = DresClient.__new__(DresClient)
    captured = {}

    def fake_request(method, path, body=None, query=None):
        captured.update(method=method, path=path, body=body, query=query)
        return {"submission": "CORRECT"}

    monkeypatch.setattr(client, "_request", fake_request)
    result = client.submit_qa("eval-1", "chim quý hiếm", "L25_V001", 12500, "session")
    assert result == {"submission": "CORRECT"}
    assert captured == {
        "method": "POST",
        "path": "/api/v2/submit/eval-1",
        "body": {
            "answerSets": [
                {"answers": [{"text": "QA-chim quý hiếm-L25_V001-12500"}]}
            ]
        },
        "query": {"session": "session"},
    }


def test_submit_trake_builds_ordered_dres_text_contract(monkeypatch) -> None:
    client = DresClient.__new__(DresClient)
    captured = {}

    def fake_request(method, path, body=None, query=None):
        captured.update(method=method, path=path, body=body, query=query)
        return {"submission": "CORRECT"}

    monkeypatch.setattr(client, "_request", fake_request)
    result = client.submit_trake(
        "eval-1", "L24_V041", [439, 812, 1200], "session"
    )
    assert result == {"submission": "CORRECT"}
    assert captured == {
        "method": "POST",
        "path": "/api/v2/submit/eval-1",
        "body": {
            "answerSets": [
                {"answers": [{"text": "TR-L24_V041-439,812,1200"}]}
            ]
        },
        "query": {"session": "session"},
    }


def _test_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(dres_bp)
    return app


def test_qa_route_requires_nonempty_answer(monkeypatch) -> None:
    from app.routes import dres

    monkeypatch.setattr(
        dres.dres_client,
        "list_evaluations",
        lambda _session: [{"id": "eval-1", "status": "ACTIVE"}],
    )
    response = _test_app().test_client().post(
        "/api/dres/submit/qa",
        json={"video_path": "L25_V001", "timestamp": 12.5, "sessionId": "session"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["message"] == "answer required for QA"


def test_qa_route_forwards_answer_and_milliseconds(monkeypatch) -> None:
    from app.routes import dres

    captured = {}
    monkeypatch.setattr(
        dres.dres_client,
        "list_evaluations",
        lambda _session: [{"id": "eval-1", "status": "ACTIVE"}],
    )

    def fake_submit_qa(evaluation_id, answer, video_id, time_ms, session_id):
        captured.update(
            evaluation_id=evaluation_id,
            answer=answer,
            video_id=video_id,
            time_ms=time_ms,
            session_id=session_id,
        )
        return {"submission": "CORRECT"}

    monkeypatch.setattr(dres.dres_client, "submit_qa", fake_submit_qa)
    response = _test_app().test_client().post(
        "/api/dres/submit/qa",
        json={
            "answer": " chim quý hiếm ",
            "video_path": "L25_V001",
            "timestamp": 12.5,
            "sessionId": "session",
        },
    )
    assert response.status_code == 200
    assert captured == {
        "evaluation_id": "eval-1",
        "answer": "chim quý hiếm",
        "video_id": "L25_V001",
        "time_ms": 12500,
        "session_id": "session",
    }


def test_submit_route_uses_explicit_evaluation_without_listing(monkeypatch) -> None:
    from app.routes import dres

    captured = {}

    def fail_if_called(_session):
        raise AssertionError("evaluation list must not be queried when an ID is explicit")

    def fake_submit(evaluation_id, video_id, time_ms, session_id):
        captured.update(
            evaluation_id=evaluation_id,
            video_id=video_id,
            time_ms=time_ms,
            session_id=session_id,
        )
        return {"submission": "CORRECT"}

    monkeypatch.setattr(dres.dres_client, "list_evaluations", fail_if_called)
    monkeypatch.setattr(dres.dres_client, "submit", fake_submit)
    response = _test_app().test_client().post(
        "/api/dres/submit/kis",
        json={
            "video_path": "L25_V001",
            "timestamp": 12.5,
            "sessionId": "session",
            "evaluationId": "new-evaluation",
        },
    )

    assert response.status_code == 200
    assert captured["evaluation_id"] == "new-evaluation"


@pytest.mark.parametrize("task_type", ["track", "trake"])
def test_trake_route_forwards_exact_order_and_evaluation(monkeypatch, task_type) -> None:
    from app.routes import dres

    captured = {}

    def fail_if_called(_session):
        raise AssertionError("an explicit evaluation must not trigger discovery")

    def fake_submit_trake(evaluation_id, video_id, frame_ids, session_id):
        captured.update(
            evaluation_id=evaluation_id,
            video_id=video_id,
            frame_ids=frame_ids,
            session_id=session_id,
        )
        return {"submission": "CORRECT"}

    monkeypatch.setattr(dres.dres_client, "list_evaluations", fail_if_called)
    monkeypatch.setattr(dres.dres_client, "submit_trake", fake_submit_trake)
    response = _test_app().test_client().post(
        f"/api/dres/submit/{task_type}",
        json={
            "video_path": "L24_V041",
            "frame_ids": [439, 812, 1200],
            "sessionId": "session",
            "evaluationId": "new-evaluation",
        },
    )

    assert response.status_code == 200
    assert captured == {
        "evaluation_id": "new-evaluation",
        "video_id": "L24_V041",
        "frame_ids": [439, 812, 1200],
        "session_id": "session",
    }
    assert response.get_json()["trakeText"] == "TR-L24_V041-439,812,1200"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"frame_ids": [439], "sessionId": "session"},
            "video_path required for TRAKE",
        ),
        (
            {"video_path": "L24_V041", "sessionId": "session"},
            "frame_ids required for TRAKE",
        ),
        (
            {
                "video_path": "L24_V041",
                "frame_ids": [439, "bad"],
                "sessionId": "session",
            },
            "frame_ids must be integers",
        ),
    ],
)
def test_trake_route_rejects_invalid_payload(payload, message) -> None:
    response = _test_app().test_client().post("/api/dres/submit/track", json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"]["message"] == message


def test_trake_route_propagates_dres_error(monkeypatch) -> None:
    from app.routes import dres

    def fail_submit(*_args):
        raise DresError(502, {"description": "DRES rejected TRAKE"})

    monkeypatch.setattr(dres.dres_client, "submit_trake", fail_submit)
    response = _test_app().test_client().post(
        "/api/dres/submit/track",
        json={
            "video_path": "L24_V041",
            "frame_ids": [439, 812],
            "sessionId": "session",
            "evaluationId": "evaluation",
        },
    )

    assert response.status_code == 502
    body = response.get_json()["error"]
    assert body["code"] == "DRES_ERROR"
    assert body["details"] == {"description": "DRES rejected TRAKE"}


# The real payload DRES returned when a team submits past its correct-answer
# quota. It arrives as HTTP 404 with `status: false` — the same shape DRES
# uses for a plain duplicate — so only DRES's own wording separates the two.
FILTER_REJECTED_BODY = {
    "description": (
        "Submission 9910a5d6-6d72-4747-8411-27c8e5233431 was rejected by "
        "filter: Maximum number of correct submissions (1) exceeded for the team."
    ),
    "status": False,
}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (FILTER_REJECTED_BODY, "DRES_REJECTED"),
        ({"submission": "CORRECT", "status": True}, "DRES_CORRECT"),
        ({"submission": "WRONG", "status": True}, "DRES_WRONG"),
        ({"status": False, "description": "Already submitted."}, "DRES_DUPLICATE"),
        ({"status": True}, "DRES_ERROR"),
        ({}, "DRES_ERROR"),
        ("DRES unreachable: timed out", "DRES_ERROR"),
        # Javalin's RFC 7807 body for a missing endpoint. Its `status` is 404,
        # which must not be mistaken for the boolean False of a duplicate.
        (
            {
                "type": "https://javalin.io/documentation#endpointnotfound",
                "title": "Endpoint GET /api/v2/client/mediaItem/list not found",
                "status": 404,
                "details": {},
            },
            "DRES_ERROR",
        ),
    ],
)
def test_verdict_code_classifies_dres_outcomes(body, expected) -> None:
    assert verdict_code(body) == expected


def test_framework_problem_body_surfaces_its_title(monkeypatch) -> None:
    """A Javalin 404 explains itself in `title`, not `description`."""
    from app.routes import dres

    def missing_endpoint(*_args):
        raise DresError(404, {
            "type": "https://javalin.io/documentation#endpointnotfound",
            "title": "Endpoint GET /api/v2/client/mediaItem/list not found",
            "status": 404,
            "details": {},
        })

    monkeypatch.setattr(dres.dres_client, "list_media_items", missing_endpoint)
    response = _test_app().test_client().get(
        "/api/dres/media-items?session=session"
    )

    assert response.status_code == 404
    error = response.get_json()["error"]
    assert error["code"] == "DRES_ERROR"
    assert error["message"] == "Endpoint GET /api/v2/client/mediaItem/list not found"


def test_filter_rejection_surfaces_reason_and_rejected_code(monkeypatch) -> None:
    """A quota rejection must never reach the user as a bare 404."""
    from app.routes import dres

    def reject(*_args):
        raise DresError(404, dict(FILTER_REJECTED_BODY))

    monkeypatch.setattr(dres.dres_client, "submit_trake", reject)
    response = _test_app().test_client().post(
        "/api/dres/submit/track",
        json={
            "video_path": "L24_V041",
            "frame_ids": [439],
            "sessionId": "session",
            "evaluationId": "evaluation",
        },
    )

    assert response.status_code == 404
    error = response.get_json()["error"]
    assert error["code"] == "DRES_REJECTED"
    assert "Maximum number of correct submissions (1) exceeded" in error["message"]
    assert error["details"] == FILTER_REJECTED_BODY


def test_transport_failure_keeps_dres_error_code_and_reason(monkeypatch) -> None:
    from app.routes import dres

    def unreachable(*_args):
        raise DresError(0, "DRES unreachable: <urlopen error timed out>")

    monkeypatch.setattr(dres.dres_client, "submit", unreachable)
    response = _test_app().test_client().post(
        "/api/dres/submit/kis",
        json={
            "video_path": "L25_V001",
            "timestamp": 12.5,
            "sessionId": "session",
            "evaluationId": "evaluation",
        },
    )

    assert response.status_code == 502
    error = response.get_json()["error"]
    assert error["code"] == "DRES_ERROR"
    assert "timed out" in error["message"]


@pytest.mark.parametrize(
    ("dres_result", "expected"),
    [
        ({"submission": "CORRECT", "status": True}, "DRES_CORRECT"),
        ({"submission": "WRONG", "status": True}, "DRES_WRONG"),
        ({"status": False, "description": "Already submitted."}, "DRES_DUPLICATE"),
    ],
)
def test_successful_response_carries_verdict_code(monkeypatch, dres_result, expected) -> None:
    from app.routes import dres

    monkeypatch.setattr(dres.dres_client, "submit", lambda *_args: dict(dres_result))
    response = _test_app().test_client().post(
        "/api/dres/submit/kis",
        json={
            "video_path": "L25_V001",
            "timestamp": 12.5,
            "sessionId": "session",
            "evaluationId": "evaluation",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["code"] == expected
