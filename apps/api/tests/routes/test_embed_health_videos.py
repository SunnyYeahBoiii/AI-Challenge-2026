from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any

import numpy as np

from app.main import create_app
from app.routes import embed as embed_routes
from app.routes import health as health_routes
from app.routes import videos as video_routes
from app.services.model_registry import ModelLoadError, ModelSpec


def _registry() -> Any:
    spec = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake", weight=1.5)
    return SimpleNamespace(enabled_specs=lambda: [spec])


def test_embed_text_success_validation_and_failure(monkeypatch: Any) -> None:
    monkeypatch.setattr(embed_routes, "get_model_registry", _registry)
    monkeypatch.setattr(
        embed_routes,
        "embed_text",
        lambda texts, model_id: np.asarray([[0.25, 0.75]], dtype=np.float32),
    )
    monkeypatch.setattr(embed_routes, "enhance_query", lambda text: f"enhanced {text}")
    client = create_app().test_client()

    invalid = client.post("/api/embed/text", json={"text": ""})
    assert invalid.status_code == 400
    success = client.post("/api/embed/text", json={"text": "query"})
    assert success.status_code == 200
    assert success.get_json()["vector"] == [0.25, 0.75]
    assert success.get_json()["enhanced"] is True

    monkeypatch.setattr(
        embed_routes,
        "embed_text",
        lambda *args: (_ for _ in ()).throw(ModelLoadError("weights missing")),
    )
    failed = client.post("/api/embed/text", json={"text": "query", "enhance": False})
    assert failed.status_code == 422


def test_embed_image_success_invalid_and_failure(monkeypatch: Any) -> None:
    monkeypatch.setattr(embed_routes, "get_model_registry", _registry)
    monkeypatch.setattr(
        embed_routes,
        "embed_image",
        lambda image_bytes, model_id: np.asarray([0.1, 0.9], dtype=np.float32),
    )
    client = create_app().test_client()
    assert client.post("/api/embed/image").status_code == 400

    success = client.post(
        "/api/embed/image",
        data={"image": (io.BytesIO(b"pixels"), "query.png"), "model_id": "fake"},
        content_type="multipart/form-data",
    )
    assert success.status_code == 200
    assert success.get_json()["filename"] == "query.png"
    assert success.get_json()["model_id"] == "fake"

    monkeypatch.setattr(
        embed_routes,
        "embed_image",
        lambda *args: (_ for _ in ()).throw(ValueError("invalid image")),
    )
    invalid = client.post(
        "/api/embed/image",
        data={"image": (io.BytesIO(b"x"), "x.png")},
        content_type="multipart/form-data",
    )
    assert invalid.status_code == 400

    monkeypatch.setattr(
        embed_routes,
        "embed_image",
        lambda *args: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    failed = client.post(
        "/api/embed/image",
        data={"image": (io.BytesIO(b"x"), "x.png")},
        content_type="multipart/form-data",
    )
    assert failed.status_code == 422


def test_models_route_exposes_reproducible_specs(monkeypatch: Any) -> None:
    monkeypatch.setattr(embed_routes, "get_model_registry", _registry)
    response = create_app().test_client().get("/api/models")
    payload = response.get_json()
    assert payload["meta"]["total"] == 1
    assert payload["data"][0]["collection"] == "frames_fake"
    assert payload["data"][0]["weight"] == 1.5


def test_health_reports_healthy_degraded_and_invalid_configuration(monkeypatch: Any) -> None:
    health_module: Any = health_routes
    spec = _registry().enabled_specs()[0]
    monkeypatch.setattr(health_routes, "get_model_registry", _registry)
    monkeypatch.setattr(
        health_routes,
        "get_milvus_client",
        lambda selected: SimpleNamespace(is_connected=lambda: True),
    )
    monkeypatch.setattr(health_module.es_client, "is_connected", lambda: True)
    client = create_app().test_client()

    healthy = client.get("/api/health").get_json()
    assert healthy["status"] == "healthy"
    assert healthy["models"] == {spec.model_id: "connected"}

    monkeypatch.setattr(
        health_routes,
        "get_milvus_client",
        lambda selected: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    degraded = client.get("/api/health").get_json()
    assert degraded["status"] == "degraded"
    assert degraded["models"] == {spec.model_id: "disconnected"}

    monkeypatch.setattr(
        health_routes,
        "get_model_registry",
        lambda: (_ for _ in ()).throw(RuntimeError("bad config")),
    )
    invalid = client.get("/api/health").get_json()
    assert invalid["models"] == {"configuration": "invalid"}


def test_video_routes_search_parse_tags_validate_size_and_404(monkeypatch: Any) -> None:
    videos_module: Any = video_routes
    captured: dict[str, Any] = {}

    def search_videos(**kwargs: Any) -> list[dict[str, Any]]:
        captured.update(kwargs)
        return [{"_source": {"video_id": "V1"}}]

    monkeypatch.setattr(videos_module.es_client, "search_videos", search_videos)
    monkeypatch.setattr(
        videos_module.es_client,
        "get_video",
        lambda video_id: {"video_id": video_id} if video_id == "V1" else None,
    )
    client = create_app().test_client()

    response = client.get("/api/videos?q=car&tags=red,street&size=7")
    assert response.status_code == 200
    assert captured == {"query": "car", "tags": ["red", "street"], "size": 7}
    assert client.get("/api/videos?size=bad").status_code == 400
    assert client.get("/api/videos?size=0").status_code == 400
    assert client.get("/api/videos/V1").get_json()["video_id"] == "V1"
    assert client.get("/api/videos/missing").status_code == 404
