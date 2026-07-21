from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.main import create_app
from app.routes import search as search_routes
from app.services.ensemble_search import EnsembleSearchError, EnsembleSearchResponse


def _response(query: str = "query") -> EnsembleSearchResponse:
    return EnsembleSearchResponse(
        query=query,
        query_variants=[query, "enhanced"],
        results=[{"frame_uid": "V1:00000001", "video_id": "V1", "frame_index": 1}],
        sources=["dfn5b:original", "dfn5b:enhanced"],
        models=["dfn5b"],
        errors={},
        rrf_k=60,
        candidate_top_k=200,
    )


def test_text_route_exposes_fusion_meta_and_passes_options(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_search(query: str, **kwargs: Any) -> EnsembleSearchResponse:
        captured["query"] = query
        captured.update(kwargs)
        return _response(query)

    monkeypatch.setattr(search_routes, "search_text_with_meta", fake_search)
    client = create_app().test_client()

    response = client.post(
        "/api/search",
        json={
            "text": "original query",
            "topk": 5,
            "ensemble": {"rrf_k": 42, "model_ids": ["dfn5b"]},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["meta"]["sources"] == ["dfn5b:original", "dfn5b:enhanced"]
    assert payload["results"][0]["frame_uid"] == "V1:00000001"
    assert captured["options"].rrf_k == 42
    assert captured["options"].result_top_k == 5


def test_text_route_returns_consistent_validation_error() -> None:
    client = create_app().test_client()

    response = client.post("/api/search", json={"text": "", "topk": 0})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_SEARCH_REQUEST"


def test_text_route_marks_enhanced_only_query_as_enhanced(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        search_routes,
        "search_text_with_meta",
        lambda query, **kwargs: replace(_response(query), query_variants=["enhanced query"]),
    )
    response = create_app().test_client().post(
        "/api/search",
        json={
            "text": "original query",
            "ensemble": {"preserve_original_query": False},
        },
    )

    assert response.status_code == 200
    assert response.get_json()["enhanced"] is True


def test_composed_route_uses_paper_default_text_weight(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_composed(
        query: str,
        image_bytes: bytes,
        **kwargs: Any,
    ) -> EnsembleSearchResponse:
        captured["query"] = query
        captured["image_bytes"] = image_bytes
        captured.update(kwargs)
        return _response(query)

    monkeypatch.setattr(search_routes, "search_composed_with_meta", fake_composed)
    client = create_app().test_client()

    response = client.post(
        "/api/search/composed",
        data={
            "text": "find another frame",
            "image": (io.BytesIO(b"image"), "feedback.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert captured["text_weight"] == 0.75
    assert captured["image_bytes"] == b"image"


def test_text_route_maps_ensemble_failure(monkeypatch: Any) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise EnsembleSearchError("all models failed")

    monkeypatch.setattr(search_routes, "search_text_with_meta", fail)
    response = create_app().test_client().post("/api/search", json={"text": "query"})
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "SEARCH_FAILED"


def test_image_route_validation_success_and_failures(monkeypatch: Any) -> None:
    client = create_app().test_client()
    missing = client.post("/api/search/image")
    assert missing.status_code == 400

    captured: dict[str, Any] = {}

    def fake_image(image_bytes: bytes, **kwargs: Any) -> EnsembleSearchResponse:
        captured["bytes"] = image_bytes
        captured.update(kwargs)
        return _response("")

    monkeypatch.setattr(search_routes, "search_image_with_meta", fake_image)
    success = client.post(
        "/api/search/image",
        data={
            "image": (io.BytesIO(b"pixels"), "query.png"),
            "topk": "4",
            "ensemble": '{"candidate_topk": 10}',
            "tags": ["person"],
        },
        content_type="multipart/form-data",
    )
    assert success.status_code == 200
    assert success.get_json()["filename"] == "query.png"
    assert captured["bytes"] == b"pixels"
    assert captured["options"].result_top_k == 4

    invalid = client.post(
        "/api/search/image",
        data={"image": (io.BytesIO(b"x"), "x.png"), "ensemble": "[]"},
        content_type="multipart/form-data",
    )
    assert invalid.status_code == 400

    monkeypatch.setattr(
        search_routes,
        "search_image_with_meta",
        lambda *args, **kwargs: (_ for _ in ()).throw(EnsembleSearchError("offline")),
    )
    failed = client.post(
        "/api/search/image",
        data={"image": (io.BytesIO(b"x"), "x.png")},
        content_type="multipart/form-data",
    )
    assert failed.status_code == 422

    oversized = client.post(
        "/api/search/image",
        data={"image": (io.BytesIO(b"x"), "x.png"), "topk": "1001"},
        content_type="multipart/form-data",
    )
    assert oversized.status_code == 400


def test_composed_route_validation_and_failure(monkeypatch: Any) -> None:
    client = create_app().test_client()
    assert client.post("/api/search/composed").status_code == 400
    missing_text = client.post(
        "/api/search/composed",
        data={"image": (io.BytesIO(b"x"), "x.png")},
        content_type="multipart/form-data",
    )
    assert missing_text.status_code == 400

    monkeypatch.setattr(
        search_routes,
        "search_composed_with_meta",
        lambda *args, **kwargs: (_ for _ in ()).throw(EnsembleSearchError("offline")),
    )
    failed = client.post(
        "/api/search/composed",
        data={"text": "query", "image": (io.BytesIO(b"x"), "x.png")},
        content_type="multipart/form-data",
    )
    assert failed.status_code == 422

    invalid_weight = client.post(
        "/api/search/composed",
        data={
            "text": "query",
            "text_weight": "2",
            "image": (io.BytesIO(b"x"), "x.png"),
        },
        content_type="multipart/form-data",
    )
    assert invalid_weight.status_code == 400

    non_finite_weight = client.post(
        "/api/search/composed",
        data={
            "text": "query",
            "text_weight": "nan",
            "image": (io.BytesIO(b"x"), "x.png"),
        },
        content_type="multipart/form-data",
    )
    assert non_finite_weight.status_code == 400


def test_video_similar_and_box_routes(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        search_routes,
        "search_video_frames",
        lambda video_id, frame_index, frame_range: [{"frame_uid": "video-frame"}],
    )
    monkeypatch.setattr(
        search_routes,
        "search_similar_frames",
        lambda video_id, frame_index, topk: [{"frame_uid": "similar"}],
    )
    monkeypatch.setattr(
        search_routes,
        "multi_box_search",
        lambda **kwargs: [{"frame_uid": "sequence"}],
    )
    client = create_app().test_client()

    assert client.post("/api/search/video", json={}).status_code == 400
    video = client.post(
        "/api/search/video", json={"video_id": "V1", "frame_index": 2, "range": 1}
    )
    assert video.status_code == 200
    assert video.get_json()["results"][0]["frame_uid"] == "video-frame"

    assert client.post("/api/search/similar", json={}).status_code == 400
    similar = client.post(
        "/api/search/similar", json={"video_id": "V1", "frame_index": 2}
    )
    assert similar.get_json()["results"][0]["frame_uid"] == "similar"

    assert client.post("/api/frames", json={}).status_code == 400
    frames = client.post("/api/frames", json={"box_queries": [{"text": "first"}]})
    assert frames.get_json()["results"][0]["frame_uid"] == "sequence"


def test_unexpected_api_failure_is_returned_as_json(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        search_routes,
        "search_video_frames",
        lambda *args: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    response = create_app().test_client().post(
        "/api/search/video",
        json={"video_id": "V1"},
    )

    assert response.status_code == 500
    assert response.is_json
    assert response.get_json()["error"] == {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "An unexpected server error occurred",
    }


def test_keyframe_route_serves_existing_file_and_404(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = tmp_path / "keyframes"
    path = root / "L01" / "L01_V001" / "0003.webp"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"webp")
    monkeypatch.setattr(search_routes, "KEYFRAMES_DIR", root)
    client = create_app().test_client()

    found = client.get("/api/keyframes/L01_V001/3")
    missing = client.get("/api/keyframes/L01_V001/4")

    assert found.status_code == 200
    assert found.data == b"webp"
    assert missing.status_code == 404
    assert missing.get_json()["error"]["code"] == "FRAME_NOT_FOUND"

    traversal = client.get("/api/keyframes/../3")
    assert traversal.status_code == 400


def test_box_route_rejects_empty_or_ambiguous_query_sources() -> None:
    client = create_app().test_client()
    empty = client.post("/api/frames", json={"box_queries": [{}]})
    ambiguous = client.post(
        "/api/frames",
        json={"box_queries": [{"text": "query", "image": "aW1hZ2U="}]},
    )
    assert empty.status_code == 400
    assert ambiguous.status_code == 400
    invalid_image = client.post(
        "/api/frames",
        json={"box_queries": [{"image": "not-base64"}]},
    )
    assert invalid_image.status_code == 400
