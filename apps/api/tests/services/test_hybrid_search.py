from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

import pytest

from app.services import hybrid_search as module
from app.services.ensemble_search import (
    EnsembleSearchOptions,
    EnsembleSearchResponse,
)
from app.services.hybrid_search import _best_temporal_sequence
from app.services.model_registry import ModelSpec


def _frame(uid: str, timestamp: float, score: float) -> dict[str, object]:
    return {
        "frame_uid": uid,
        "video_id": "V1",
        "frame_index": int(timestamp),
        "pts_time": timestamp,
        "score": score,
    }


def test_temporal_dp_selects_highest_scoring_ordered_sequence() -> None:
    groups = [
        [_frame("a-low", 10.0, 0.1), _frame("a-high", 20.0, 0.9)],
        [_frame("b-before", 15.0, 1.0), _frame("b-after", 25.0, 0.8)],
        [_frame("c", 30.0, 0.7)],
    ]

    sequence = _best_temporal_sequence(groups, window_seconds=20.0)

    assert [frame["frame_uid"] for frame in sequence] == ["a-high", "b-after", "c"]


def test_temporal_dp_rejects_out_of_order_only_candidates() -> None:
    groups = [[_frame("a", 20.0, 1.0)], [_frame("b", 10.0, 1.0)]]

    assert _best_temporal_sequence(groups, window_seconds=120.0) == []


def test_temporal_dp_applies_window_to_the_whole_sequence() -> None:
    groups = [
        [_frame("a", 0.0, 1.0)],
        [_frame("b", 100.0, 1.0)],
        [_frame("c", 200.0, 1.0)],
    ]

    assert _best_temporal_sequence(groups, window_seconds=120.0) == []


def _response(results: list[dict[str, Any]]) -> EnsembleSearchResponse:
    return EnsembleSearchResponse(
        query="query",
        query_variants=["query"],
        results=results,
        sources=["fake:original"],
        models=["fake"],
        errors={},
        rrf_k=60,
        candidate_top_k=200,
    )


class FakeES:
    def get_videos(self, video_ids: list[str]) -> dict[str, dict[str, object]]:
        return {
            video_id: video
            for video_id in video_ids
            if (video := self.get_video(video_id)) is not None
        }

    def get_video(self, video_id: str) -> dict[str, object] | None:
        if video_id == "V1":
            return {
                "title": "Video one",
                "description": "Description",
                "keywords": ["hello"],
                "watch_url": "fallback",
            }
        return None

    def filter_videos_by_keywords(
        self,
        video_ids: list[str],
        keywords: list[str],
        **kwargs: Any,
    ) -> list[str]:
        assert keywords == ["hello"]
        return [video_id for video_id in video_ids if video_id == "V1"]


def test_enrichment_deduplication_and_metadata_filters(monkeypatch: Any) -> None:
    monkeypatch.setattr(module, "es_client", FakeES())
    raw = [
        {
            "frame_uid": "f1",
            "video_id": "V1",
            "frame_index": 1,
            "youtube_url": "direct",
            "tags": ["Person", "Street"],
        },
        {"frame_uid": "f1", "video_id": "V1", "frame_index": 1},
        {"frame_uid": "f2", "video_id": "V2", "frame_index": 2, "tags": ["car"]},
    ]

    enriched = module._enrich_frames(raw)

    assert len(enriched) == 2
    assert enriched[0]["title"] == "Video one"
    assert enriched[0]["watch_url"] == "direct"
    assert enriched[0]["thumbnail_url"] == "/api/keyframes/V1/1"
    assert module._filter_tags(enriched, ["person", "street"], "and") == [enriched[0]]
    assert module._filter_tags(enriched, ["street", "car"], "or") == enriched
    assert module._filter_tags(enriched, None, "and") == enriched
    assert module._filter_keywords(enriched, ["hello"], "and", "all") == [enriched[0]]
    assert module._filter_keywords([], ["hello"], "and", "all") == []


def test_candidate_expansion_and_postprocessing(monkeypatch: Any) -> None:
    options = EnsembleSearchOptions(
        candidate_top_k=100,
        result_top_k=2,
        min_time_gap_seconds=2.0,
        max_per_video=1,
    )
    expanded = module._candidate_options(options, has_filters=True)
    unchanged = module._candidate_options(options, has_filters=False)
    assert expanded.result_top_k == 8
    assert expanded.min_time_gap_seconds == 0.0
    assert unchanged.result_top_k == 2

    monkeypatch.setattr(module, "_enrich_frames", lambda frames: list(frames))
    monkeypatch.setattr(module, "_filter_tags", lambda frames, tags, mode: list(frames))
    monkeypatch.setattr(
        module,
        "_filter_keywords",
        lambda frames, keywords, mode, source: list(frames),
    )
    response = _response(
        [
            {"frame_uid": "f1", "video_id": "V1", "pts_time": 1.0},
            {"frame_uid": "f2", "video_id": "V1", "pts_time": 10.0},
            {"frame_uid": "f3", "video_id": "V2", "pts_time": 1.0},
        ]
    )
    processed = module._postprocess_response(
        response,
        options,
        tags=None,
        tag_mode="and",
        keywords=None,
        keyword_mode="and",
        keyword_source="all",
    )
    assert [frame["frame_uid"] for frame in processed.results] == ["f1", "f3"]


class FakeEnsembleService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def search_text(
        self, query: str, options: EnsembleSearchOptions
    ) -> EnsembleSearchResponse:
        self.calls.append(("text", options))
        return _response([{"frame_uid": "t", "video_id": "V1", "frame_index": 1}])

    def search_image(
        self, image: object, options: EnsembleSearchOptions
    ) -> EnsembleSearchResponse:
        self.calls.append(("image", options))
        return _response([{"frame_uid": "i", "video_id": "V1", "frame_index": 1}])

    def search_composed(
        self,
        query: str,
        image: object,
        *,
        original_query: str | None = None,
        text_weight: float,
        options: EnsembleSearchOptions,
    ) -> EnsembleSearchResponse:
        self.calls.append(("composed", (original_query, text_weight)))
        return _response([{"frame_uid": "c", "video_id": "V1", "frame_index": 1}])


def test_online_search_entrypoints_and_compatibility_wrappers(monkeypatch: Any) -> None:
    service = FakeEnsembleService()
    monkeypatch.setattr(module, "get_ensemble_search_service", lambda: service)
    monkeypatch.setattr(module, "decode_image", lambda payload: ("decoded", payload))
    monkeypatch.setattr(module, "_postprocess_response", lambda response, *args, **kwargs: response)
    monkeypatch.setattr(module, "_enrich_frames", lambda frames: list(frames))
    options = EnsembleSearchOptions(result_top_k=5)

    assert module.search_text_with_meta("q", options=options).results[0]["frame_uid"] == "t"
    assert module.search_image_with_meta(b"image", options=options).results[0]["frame_uid"] == "i"
    assert module.search_composed_with_meta(
        "feedback",
        b"image",
        original_query="original",
        text_weight=0.75,
        options=options,
    ).results[0]["frame_uid"] == "c"
    assert module.search_text("q", topk=3, enhance=False)[0]["frame_uid"] == "t"
    assert module.search_image(b"image", topk=4)[0]["frame_uid"] == "i"
    first_options: Any = service.calls[0][1]
    assert first_options.result_top_k == 5


def test_ensemble_service_singleton_and_reset(monkeypatch: Any) -> None:
    created: list[tuple[object, object, object]] = []

    class Service:
        def __init__(self, **kwargs: Any) -> None:
            created.append(
                (kwargs["registry"], kwargs["vector_backend"], kwargs["embedding_cache"])
            )

    monkeypatch.setattr(module, "EnsembleSearchService", Service)
    monkeypatch.setattr(module, "get_model_registry", lambda: "registry")
    monkeypatch.setattr(module, "get_vector_backend", lambda: "backend")
    module.reset_ensemble_search_service()
    first = module.get_ensemble_search_service()
    assert module.get_ensemble_search_service() is first
    assert created[0][0:2] == ("registry", "backend")
    module.reset_ensemble_search_service()


def test_video_frame_window_and_missing_position(monkeypatch: Any) -> None:
    frames = [
        {"frame_uid": f"f{i}", "video_id": "V1", "frame_index": i}
        for i in [3, 1, 2, 4]
    ]
    calls: list[tuple[str, int | None, int]] = []

    def list_video_frames(
        video_id: str,
        *,
        frame_index: int | None = None,
        frame_range: int = 5,
    ) -> list[dict[str, Any]]:
        calls.append((video_id, frame_index, frame_range))
        return frames

    client = SimpleNamespace(list_video_frames=list_video_frames)
    monkeypatch.setattr(module, "get_milvus_client", lambda spec=None: client)
    monkeypatch.setattr(module, "_enrich_frames", lambda values: list(values))

    assert [frame["frame_index"] for frame in module.search_video_frames("V1")] == [1, 2, 3, 4]
    assert [frame["frame_index"] for frame in module.search_video_frames("V1", 2, 1)] == [1, 2, 3]
    assert len(module.search_video_frames("V1", 99, 1)) == 4
    assert calls == [("V1", None, 5), ("V1", 2, 1), ("V1", 99, 1)]


def test_similar_search_fuses_available_models_and_removes_query_frame(monkeypatch: Any) -> None:
    specs = [
        ModelSpec("a", "fake", "a", 1, "a", weight=1.0),
        ModelSpec("b", "fake", "b", 1, "b", weight=1.0),
    ]
    registry = SimpleNamespace(enabled_specs=lambda: specs)

    class Client:
        def __init__(self, spec: ModelSpec) -> None:
            self.spec = spec

        def get_frame_embedding(self, video_id: str, frame_index: int) -> list[float] | None:
            return [1.0] if self.spec.model_id == "a" else None

    class Backend:
        def search(self, spec: object, embedding: object, top_k: int) -> list[dict[str, Any]]:
            return [
                {"frame_uid": "source", "video_id": "V1", "frame_index": 2},
                {"frame_uid": "other", "video_id": "V2", "frame_index": 5},
            ]

    monkeypatch.setattr(module, "get_model_registry", lambda: registry)
    monkeypatch.setattr(module, "get_vector_backend", lambda: Backend())
    monkeypatch.setattr(module, "get_milvus_client", lambda spec=None: Client(spec))
    monkeypatch.setattr(module, "_enrich_frames", lambda frames: list(frames))

    results = module.search_similar_frames("V1", 2, topk=3)
    assert [frame["frame_uid"] for frame in results] == ["other"]


def test_similar_search_skips_zero_weight_and_failed_models(monkeypatch: Any) -> None:
    specs = [
        ModelSpec("zero", "fake", "zero", 1, "zero", weight=0.0),
        ModelSpec("broken", "fake", "broken", 1, "broken", weight=1.0),
        ModelSpec("good", "fake", "good", 1, "good", weight=1.0),
    ]
    monkeypatch.setattr(
        module,
        "get_model_registry",
        lambda: SimpleNamespace(enabled_specs=lambda: specs),
    )

    class Client:
        def __init__(self, spec: ModelSpec) -> None:
            self.spec = spec

        def get_frame_embedding(self, video_id: str, frame_index: int) -> list[float] | None:
            del video_id, frame_index
            if self.spec.model_id == "broken":
                raise RuntimeError("collection offline")
            return [1.0]

    class Backend:
        def search(self, spec: ModelSpec, embedding: object, top_k: int) -> list[dict[str, Any]]:
            del embedding, top_k
            return [{"frame_uid": spec.model_id, "video_id": "V2", "frame_index": 1}]

    monkeypatch.setattr(module, "get_milvus_client", lambda spec=None: Client(spec))
    monkeypatch.setattr(module, "get_vector_backend", lambda: Backend())
    monkeypatch.setattr(module, "_enrich_frames", lambda frames: list(frames))

    results = module.search_similar_frames("V1", 2)

    assert [frame["frame_uid"] for frame in results] == ["good"]


def test_box_image_decode_and_temporal_merge_uses_fusion_score() -> None:
    payload = base64.b64encode(b"image").decode()
    assert module._decode_box_image(f"data:image/png;base64,{payload}") == b"image"
    with pytest.raises(Exception):
        module._decode_box_image("not base64!")

    per_box = [
        [
            {"frame_uid": "a1", "video_id": "V1", "pts_time": 1.0, "fusion_score": 0.9},
            {"frame_uid": "a2", "video_id": "V2", "pts_time": 1.0, "fusion_score": 0.2},
        ],
        [
            {"frame_uid": "b1", "video_id": "V1", "pts_time": 2.0, "fusion_score": 0.7},
            {"frame_uid": "b2", "video_id": "V2", "pts_time": 2.0, "fusion_score": 0.1},
        ],
    ]
    merged = module._merge_temporal_sequences(per_box, 10.0)
    assert [frame["frame_uid"] for frame in merged[:2]] == ["a1", "b1"]
    assert merged[0]["score"] == pytest.approx(0.8)
    assert merged[1]["sequence_idx"] == 1
    assert module._merge_temporal_sequences([], 10.0) == []


def test_multi_box_search_handles_text_image_single_and_empty(monkeypatch: Any) -> None:
    text_calls: list[dict[str, Any]] = []
    image_calls: list[dict[str, Any]] = []

    def fake_text(**kwargs: Any) -> list[dict[str, Any]]:
        text_calls.append(kwargs)
        return [{"frame_uid": "t", "video_id": "V1", "pts_time": 1.0, "score": 1.0}]

    def fake_image(**kwargs: Any) -> list[dict[str, Any]]:
        image_calls.append(kwargs)
        return [{"frame_uid": "i", "video_id": "V1", "pts_time": 2.0, "score": 1.0}]

    monkeypatch.setattr(module, "search_text", fake_text)
    monkeypatch.setattr(module, "search_image", fake_image)
    encoded = base64.b64encode(b"image").decode()

    assert module.multi_box_search([]) == []
    single = module.multi_box_search([{"text": "first", "enhance": False}], enhance=True)
    assert single[0]["frame_uid"] == "t"
    merged = module.multi_box_search(
        [{"text": "first", "topk": 7}, {"image": encoded, "topk": 8}],
        temporal_window=10.0,
    )
    assert [frame["frame_uid"] for frame in merged] == ["t", "i"]
    assert text_calls[-1]["topk"] == 7
    assert image_calls[-1]["image_bytes"] == b"image"
