from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services import milvus_client as module
from app.services.model_registry import ModelSpec


SPEC = ModelSpec("fake", "fake", "fake/model", 2, "frames_fake")


class FakeHit:
    def __init__(self, hit_id: int, score: float, data: dict[str, Any]) -> None:
        self.id = hit_id
        self.score = score
        self.entity = data


class FakeCollection:
    def __init__(self, fields: list[str] | None = None, *, dimension: int = 2) -> None:
        names = fields or ["video_id", "frame_index", "tags", "embedding"]
        schema_fields = []
        for name in names:
            params = {"dim": dimension} if name == "embedding" else {}
            schema_fields.append(SimpleNamespace(name=name, params=params))
        self.schema = SimpleNamespace(fields=schema_fields)
        self.loaded = False
        self.search_calls: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, Any]] = []
        self.search_result: list[list[FakeHit]] = [[]]
        self.query_results: list[list[dict[str, Any]]] = []
        self.index_calls: list[dict[str, Any]] = []
        self.iterator_calls: list[dict[str, Any]] = []
        self.iterator_batches: list[list[dict[str, Any]]] = []

    def load(self) -> None:
        self.loaded = True

    def search(self, **kwargs: Any) -> list[list[FakeHit]]:
        self.search_calls.append(kwargs)
        return self.search_result

    def query(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.query_calls.append(kwargs)
        return self.query_results.pop(0)

    def create_index(self, **kwargs: Any) -> None:
        self.index_calls.append(kwargs)

    def query_iterator(self, **kwargs: Any) -> Any:
        self.iterator_calls.append(kwargs)
        batches = list(self.iterator_batches)

        class Iterator:
            closed = False

            def next(self) -> list[dict[str, Any]]:
                return batches.pop(0) if batches else []

            def close(self) -> None:
                self.closed = True

        return Iterator()


def test_connect_uses_optional_token_and_escaping(monkeypatch: Any) -> None:
    calls: list[dict[str, object]] = []
    sdk: Any = module
    monkeypatch.setattr(sdk.connections, "connect", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(module, "MILVUS_TOKEN", "secret")

    module._connect()

    assert calls[0]["token"] == "secret"
    assert module._escape_string('a\\b"c') == 'a\\\\b\\"c'


def test_collection_search_validates_shape_and_normalizes_legacy_hits(monkeypatch: Any) -> None:
    fake = FakeCollection()
    fake.search_result = [[FakeHit(9, 0.75, {"video_id": "V1", "frame_index": 3, "tags": None})]]
    monkeypatch.setattr(module, "_connect", lambda: None)
    monkeypatch.setattr(module, "Collection", lambda name: fake)
    client = module.MilvusCollectionClient(SPEC)

    with pytest.raises(ValueError, match="expects 2"):
        client.search([1.0])
    results = client.search([1.0, 0.0], top_k=4, expression='video_id == "V1"')

    assert fake.loaded is True
    assert results[0]["frame_uid"] == "V1:00000003"
    assert results[0]["id"] == "9"
    assert results[0]["tags"] == []
    assert results[0]["vector_score"] == 0.75
    assert fake.search_calls[0]["limit"] == 4


def test_embedding_lookup_and_video_listing(monkeypatch: Any) -> None:
    fake = FakeCollection(["frame_uid", "video_id", "frame_index", "tags", "embedding"])
    fake.query_results = [
        [{"embedding": [0.25, 0.75]}],
        [],
        [{"video_id": "V1", "frame_index": 2, "tags": None}],
    ]
    monkeypatch.setattr(module, "_connect", lambda: None)
    monkeypatch.setattr(module, "Collection", lambda name: fake)
    sdk: Any = module
    monkeypatch.setattr(sdk.utility, "has_collection", lambda name: True)
    client = module.MilvusCollectionClient(SPEC)

    assert client.get_frame_embedding('V\\"1', 2) == [0.25, 0.75]
    assert client.get_frame_embedding("V1", 999) is None
    frames = client.list_video_frames("V1", limit=12, frame_index=20, frame_range=3)

    assert frames[0]["frame_uid"] == "V1:00000002"
    assert frames[0]["id"] == "V1:00000002"
    assert frames[0]["frame_idx"] == 2
    assert frames[0]["tags"] == []
    assert fake.query_calls[-1]["limit"] == 7
    assert "frame_index >= 17" in fake.query_calls[-1]["expr"]
    assert "frame_index <= 23" in fake.query_calls[-1]["expr"]
    assert client.is_connected() is True

    with pytest.raises(ValueError, match="frame_range"):
        client.list_video_frames("V1", frame_index=1, frame_range=-1)


def test_full_video_listing_uses_iterator_without_silent_16k_cap(monkeypatch: Any) -> None:
    fake = FakeCollection(["frame_uid", "video_id", "frame_index", "embedding"])
    fake.iterator_batches = [
        [{"video_id": "V1", "frame_index": 1}],
        [{"video_id": "V1", "frame_index": 20_000}],
    ]
    monkeypatch.setattr(module, "_connect", lambda: None)
    monkeypatch.setattr(module, "Collection", lambda name: fake)
    client = module.MilvusCollectionClient(SPEC)

    frames = client.list_video_frames("V1")

    assert [frame["frame_index"] for frame in frames] == [1, 20_000]
    assert fake.iterator_calls[0]["limit"] == -1
    assert fake.iterator_calls[0]["batch_size"] == 1_000

    with pytest.raises(ValueError, match="limit"):
        client.list_video_frames("V1", limit=0)


def test_existing_collection_validation_and_recreate(monkeypatch: Any) -> None:
    existing = FakeCollection(["video_id", "embedding"], dimension=3)
    monkeypatch.setattr(module, "_connect", lambda: None)
    monkeypatch.setattr(module, "Collection", lambda *args, **kwargs: existing)
    sdk: Any = module
    monkeypatch.setattr(sdk.utility, "has_collection", lambda name: True)
    dropped: list[str] = []
    monkeypatch.setattr(sdk.utility, "drop_collection", dropped.append)

    with pytest.raises(ValueError, match="dimension"):
        module.ensure_model_collection(SPEC)

    existing.schema.fields[-1].params["dim"] = 2
    with pytest.raises(ValueError, match="canonical"):
        module.ensure_model_collection(SPEC, require_canonical_schema=True)

    module.ensure_model_collection(SPEC, recreate=True)
    assert dropped == ["frames_fake"]


def test_create_collection_builds_canonical_schema_and_index(monkeypatch: Any) -> None:
    created = FakeCollection(["frame_uid", "embedding"])
    captured: dict[str, Any] = {}
    monkeypatch.setattr(module, "_connect", lambda: None)
    sdk: Any = module
    monkeypatch.setattr(sdk.utility, "has_collection", lambda name: False)
    monkeypatch.setattr(module, "FieldSchema", lambda **kwargs: kwargs)
    monkeypatch.setattr(module, "CollectionSchema", lambda fields, **kwargs: {"fields": fields, **kwargs})

    def collection(name: str, schema: object) -> FakeCollection:
        captured["name"] = name
        captured["schema"] = schema
        return created

    monkeypatch.setattr(module, "Collection", collection)

    result = module.ensure_model_collection(SPEC)

    assert result is created
    assert captured["name"] == "frames_fake"
    assert captured["schema"]["fields"][0]["name"] == "frame_uid"
    assert created.index_calls[0]["index_params"]["metric_type"] == "IP"


def test_client_and_backend_caches(monkeypatch: Any) -> None:
    module.reset_milvus_clients()
    created: list[object] = []

    class StubClient:
        def __init__(self, spec: ModelSpec) -> None:
            self.spec = spec
            created.append(self)

        def search(self, embedding: object, **kwargs: Any) -> list[dict[str, Any]]:
            return [{"frame_uid": "f"}]

    monkeypatch.setattr(module, "MilvusCollectionClient", StubClient)
    first = module.get_milvus_client(SPEC)
    second = module.get_milvus_client(SPEC)
    backend = module.get_vector_backend()

    assert first is second
    assert len(created) == 1
    assert backend.search(SPEC, [1.0, 0.0], 5) == [{"frame_uid": "f"}]
    assert module.get_vector_backend() is backend
    module.reset_milvus_clients()
