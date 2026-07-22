from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pytest

from app.services.ensemble_search import (
    EnsembleSearchError,
    EnsembleSearchOptions,
    EnsembleSearchService,
)
from app.services.model_registry import EmbeddingModel, ModelRegistry, ModelSpec


class FakeModel(EmbeddingModel):
    def __init__(self, spec: ModelSpec, offset: float) -> None:
        self.spec = spec
        self.offset = offset

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        values = [self.offset + (2.0 if text == "enhanced" else 1.0) for text in texts]
        return np.asarray(values, dtype=np.float32).reshape(-1, 1)

    def encode_images(self, images: list[object]) -> np.ndarray:
        return np.full((len(images), 1), self.offset + 3.0, dtype=np.float32)


class FakeVectorBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float, int]] = []

    def search(
        self,
        spec: ModelSpec,
        embedding: Sequence[float],
        top_k: int,
        expression: str | None = None,
    ) -> list[dict[str, object]]:
        del expression
        value = float(embedding[0])
        self.calls.append((spec.model_id, value, top_k))
        if spec.model_id == "a":
            ids = ["shared", "only-a"] if value == 1.0 else ["only-a", "shared"]
        else:
            ids = ["shared", "only-b"] if value == 11.0 else ["only-b", "shared"]
        return [
            {
                "frame_uid": frame_uid,
                "video_id": frame_uid,
                "frame_index": rank,
                "pts_time": float(rank),
                "vector_score": 1.0 / rank,
            }
            for rank, frame_uid in enumerate(ids, start=1)
        ]


def _registry() -> ModelRegistry:
    specs = [
        ModelSpec("a", "fake-a", "a", 1, "frames_a", weight=1.0),
        ModelSpec("b", "fake-b", "b", 1, "frames_b", weight=2.0),
    ]
    return ModelRegistry(
        specs,
        factories={
            "fake-a": lambda spec: FakeModel(spec, 0.0),
            "fake-b": lambda spec: FakeModel(spec, 10.0),
        },
    )


def test_text_search_fans_out_models_and_query_variants_then_fuses() -> None:
    backend = FakeVectorBackend()
    service = EnsembleSearchService(
        registry=_registry(),
        vector_backend=backend,
        query_enhancer=lambda query: "enhanced",
    )
    options = EnsembleSearchOptions(
        candidate_top_k=20,
        result_top_k=10,
        use_enhanced_query=True,
        preserve_original_query=True,
        rrf_k=60,
    )

    response = service.search_text("original", options)

    assert response.query_variants == ["original", "enhanced"]
    assert len(backend.calls) == 4
    assert response.results[0]["frame_uid"] == "shared"
    assert set(response.results[0]["model_ranks"]) == {"a", "b"}
    assert response.sources == ["a:original", "a:enhanced", "b:original", "b:enhanced"]


def test_composed_search_fuses_text_and_image_per_model_before_rrf() -> None:
    backend = FakeVectorBackend()
    service = EnsembleSearchService(
        registry=_registry(),
        vector_backend=backend,
        query_enhancer=lambda query: query,
    )
    options = EnsembleSearchOptions(candidate_top_k=10, result_top_k=10)

    response = service.search_composed("original", object(), text_weight=0.75, options=options)

    assert len(backend.calls) == 2
    assert backend.calls[0][1] == pytest.approx(1.0)
    assert backend.calls[1][1] == pytest.approx(1.0)
    assert response.sources == ["a:composed", "b:composed"]
    assert response.meta()["compositionModes"] == {
        "a": "linear_text_image",
        "b": "linear_text_image",
    }


def test_composed_search_prefers_model_native_joint_encoder() -> None:
    encoded_texts: list[str] = []

    class JointModel(FakeModel):
        def encode_texts(self, texts: list[str]) -> np.ndarray:
            raise AssertionError("linear text encoder must not be used")

        def encode_images(self, images: list[object]) -> np.ndarray:
            raise AssertionError("linear image encoder must not be used")

        def encode_composed(
            self, images: list[object], texts: list[str]
        ) -> np.ndarray | None:
            assert len(images) == len(texts) == 1
            encoded_texts.extend(texts)
            return np.asarray([[1.0]], dtype=np.float32)

    registry = ModelRegistry(
        [ModelSpec("joint", "joint", "joint", 1, "joint")],
        factories={"joint": lambda spec: JointModel(spec, 0.0)},
    )
    backend = FakeVectorBackend()
    service = EnsembleSearchService(
        registry=registry,
        vector_backend=backend,
        query_enhancer=lambda query: query,
    )

    response = service.search_composed(
        "Change the shirt to green.",
        object(),
        original_query="The dog is surfing.",
        text_weight=0.75,
        options=EnsembleSearchOptions(use_enhanced_query=False),
    )

    assert encoded_texts == ["The dog is surfing. Change the shirt to green."]
    assert response.query == "The dog is surfing. Change the shirt to green."
    assert response.sources == ["joint:joint-composed"]
    assert response.meta()["compositionModes"] == {"joint": "joint_image_text"}
    assert response.meta()["compositionInput"] == {
        "originalQuery": "The dog is surfing.",
        "feedbackText": "Change the shirt to green.",
        "contextQuery": "The dog is surfing. Change the shirt to green.",
        "encodedText": "The dog is surfing. Change the shirt to green.",
    }


def test_top1_composed_profile_encodes_feedback_without_original_query() -> None:
    encoded_texts: list[str] = []

    class CapturingModel(FakeModel):
        def encode_texts(self, texts: list[str]) -> np.ndarray:
            encoded_texts.extend(texts)
            return super().encode_texts(texts)

    registry = ModelRegistry(
        [ModelSpec("linear", "linear", "linear", 1, "linear")],
        factories={"linear": lambda spec: CapturingModel(spec, 0.0)},
    )
    service = EnsembleSearchService(
        registry=registry,
        vector_backend=SimpleBackend(),
        query_enhancer=lambda query: query,
    )

    response = service.search_composed(
        "Change the shirt to green.",
        object(),
        original_query="The dog is surfing.",
        text_weight=0.75,
        options=EnsembleSearchOptions(
            profile="top1_2025",
            use_enhanced_query=False,
        ),
    )

    assert encoded_texts == ["Change the shirt to green."]
    assert response.query == "Change the shirt to green."
    assert response.meta()["compositionInput"] == {
        "originalQuery": "The dog is surfing.",
        "feedbackText": "Change the shirt to green.",
        "contextQuery": "The dog is surfing. Change the shirt to green.",
        "encodedText": "Change the shirt to green.",
    }


def test_invalid_native_composed_shape_becomes_a_model_error() -> None:
    class InvalidJointModel(FakeModel):
        def encode_composed(
            self, images: list[object], texts: list[str]
        ) -> np.ndarray | None:
            return np.ones((1, 2), dtype=np.float32)

    registry = ModelRegistry(
        [ModelSpec("joint", "joint", "joint", 1, "joint")],
        factories={"joint": lambda spec: InvalidJointModel(spec, 0.0)},
    )
    service = EnsembleSearchService(
        registry=registry,
        vector_backend=SimpleBackend(),
        query_enhancer=lambda query: query,
    )

    with pytest.raises(EnsembleSearchError, match="returned shape"):
        service.search_composed(
            "modification", object(), text_weight=0.5, options=EnsembleSearchOptions()
        )


def test_composition_modes_only_include_successful_models() -> None:
    class FailsOneBackend(SimpleBackend):
        def search(
            self,
            spec: ModelSpec,
            embedding: Sequence[float],
            top_k: int,
            expression: str | None = None,
        ) -> list[dict[str, object]]:
            if spec.model_id == "a":
                raise RuntimeError("collection unavailable")
            return super().search(spec, embedding, top_k, expression)

    service = EnsembleSearchService(
        registry=_registry(),
        vector_backend=FailsOneBackend(),
        query_enhancer=lambda query: query,
    )

    response = service.search_composed(
        "query", object(), text_weight=0.75, options=EnsembleSearchOptions()
    )

    assert response.models == ["b"]
    assert response.composition_modes == {"b": "linear_text_image"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"candidate_top_k": 0},
        {"result_top_k": 0},
        {"rrf_k": 0},
        {"model_weights": {"a": -1.0}},
    ],
)
def test_options_validate_retrieval_controls(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        EnsembleSearchOptions(**kwargs)  # type: ignore[arg-type]


def test_text_search_supports_enhanced_only_custom_weight_expression_and_meta() -> None:
    backend = FakeVectorBackend()
    service = EnsembleSearchService(
        registry=_registry(),
        vector_backend=backend,
        query_enhancer=lambda query: " enhanced ",
    )
    options = EnsembleSearchOptions(
        model_ids=("a",),
        model_weights={"a": 3.0},
        preserve_original_query=False,
        result_top_k=1,
    )

    response = service.search_text(" original ", options, expression='video_id == "V1"')

    assert response.query == "original"
    assert response.query_variants == ["enhanced"]
    assert response.sources == ["a:enhanced"]
    assert response.models == ["a"]
    assert response.meta()["candidateTopK"] == 200
    assert len(response.results) == 1


def test_image_search_fuses_models_and_reports_metadata() -> None:
    backend = FakeVectorBackend()
    service = EnsembleSearchService(
        registry=_registry(),
        vector_backend=backend,
        query_enhancer=lambda query: query,
    )

    response = service.search_image(object(), EnsembleSearchOptions(result_top_k=2))

    assert response.query == ""
    assert response.query_variants == []
    assert response.sources == ["a:image", "b:image"]
    assert response.errors == {}
    assert len(response.results) == 2


class BrokenModel(FakeModel):
    def encode_texts(self, texts: list[str]) -> np.ndarray:
        raise RuntimeError("encoder offline")


def _partially_broken_registry() -> ModelRegistry:
    specs = [
        ModelSpec("good", "good", "good", 1, "good"),
        ModelSpec("bad", "bad", "bad", 1, "bad"),
    ]
    return ModelRegistry(
        specs,
        factories={
            "good": lambda spec: FakeModel(spec, 0.0),
            "bad": lambda spec: BrokenModel(spec, 0.0),
        },
    )


class SimpleBackend:
    def search(
        self,
        spec: ModelSpec,
        embedding: Sequence[float],
        top_k: int,
        expression: str | None = None,
    ) -> list[dict[str, object]]:
        del embedding, top_k, expression
        return [{"frame_uid": spec.model_id, "video_id": "V1", "frame_index": 1}]


def test_partial_model_failure_is_visible_and_strict_mode_fails() -> None:
    service = EnsembleSearchService(
        registry=_partially_broken_registry(),
        vector_backend=SimpleBackend(),
        query_enhancer=lambda query: query,
    )

    response = service.search_text("query", EnsembleSearchOptions())
    assert response.models == ["good"]
    assert response.errors == {"bad": "encoder offline"}

    with pytest.raises(EnsembleSearchError, match="encoder offline"):
        service.search_text(
            "query",
            EnsembleSearchOptions(allow_partial_models=False),
        )


def test_text_model_failure_rolls_back_already_added_query_variants() -> None:
    class FailsSecondVariant(FakeVectorBackend):
        def search(
            self,
            spec: ModelSpec,
            embedding: Sequence[float],
            top_k: int,
            expression: str | None = None,
        ) -> list[dict[str, object]]:
            if spec.model_id == "a" and float(embedding[0]) == 2.0:
                raise RuntimeError("second variant failed")
            return super().search(spec, embedding, top_k, expression)

    service = EnsembleSearchService(
        registry=_registry(),
        vector_backend=FailsSecondVariant(),
        query_enhancer=lambda query: "enhanced",
    )

    response = service.search_text("original", EnsembleSearchOptions())

    assert response.models == ["b"]
    assert response.errors == {"a": "second variant failed"}
    assert all(source.startswith("b:") for source in response.sources)


def test_all_models_failed_empty_query_shape_and_composed_validation() -> None:
    broken = EnsembleSearchService(
        registry=ModelRegistry(
            [ModelSpec("bad", "bad", "bad", 1, "bad")],
            factories={"bad": lambda spec: BrokenModel(spec, 0.0)},
        ),
        vector_backend=SimpleBackend(),
        query_enhancer=lambda query: query,
    )
    with pytest.raises(EnsembleSearchError, match="required"):
        broken.search_text("   ", EnsembleSearchOptions())
    with pytest.raises(EnsembleSearchError, match="all embedding"):
        broken.search_text("query", EnsembleSearchOptions())
    with pytest.raises(EnsembleSearchError, match="between"):
        broken.search_composed("query", object(), text_weight=1.1, options=EnsembleSearchOptions())
    with pytest.raises(EnsembleSearchError, match="required"):
        broken.search_composed(" ", object(), text_weight=0.5, options=EnsembleSearchOptions())


def test_zero_weight_models_are_skipped_and_all_zero_is_rejected() -> None:
    backend = FakeVectorBackend()
    service = EnsembleSearchService(
        registry=_registry(),
        vector_backend=backend,
        query_enhancer=lambda query: query,
    )

    response = service.search_text(
        "query",
        EnsembleSearchOptions(model_weights={"a": 0.0, "b": 1.0}),
    )
    assert response.models == ["b"]
    assert all(call[0] == "b" for call in backend.calls)

    with pytest.raises(EnsembleSearchError, match="positive weight"):
        service.search_text(
            "query",
            EnsembleSearchOptions(model_weights={"a": 0.0, "b": 0.0}),
        )


def test_non_finite_weights_are_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        EnsembleSearchOptions(model_weights={"a": float("nan")})


def test_wrong_text_shape_and_incompatible_composed_shapes_become_model_errors() -> None:
    class WrongShape(FakeModel):
        def encode_texts(self, texts: list[str]) -> np.ndarray:
            return np.ones((1, 2), dtype=np.float32)

        def encode_images(self, images: list[object]) -> np.ndarray:
            return np.ones((1, 1), dtype=np.float32)

    registry = ModelRegistry(
        [ModelSpec("wrong", "wrong", "wrong", 2, "wrong")],
        factories={"wrong": lambda spec: WrongShape(spec, 0.0)},
    )
    service = EnsembleSearchService(
        registry=registry,
        vector_backend=SimpleBackend(),
        query_enhancer=lambda query: "enhanced",
    )

    with pytest.raises(EnsembleSearchError, match="returned shape"):
        service.search_text("query", EnsembleSearchOptions())
    with pytest.raises(EnsembleSearchError, match="returned shape"):
        service.search_image(object(), EnsembleSearchOptions())
    with pytest.raises(EnsembleSearchError, match="incompatible"):
        service.search_composed(
            "query",
            object(),
            text_weight=0.5,
            options=EnsembleSearchOptions(use_enhanced_query=False),
        )


def test_non_finite_query_embeddings_become_model_errors() -> None:
    class NonFiniteModel(FakeModel):
        def encode_texts(self, texts: list[str]) -> np.ndarray:
            return np.full((len(texts), 1), np.nan, dtype=np.float32)

        def encode_images(self, images: list[object]) -> np.ndarray:
            return np.full((len(images), 1), np.inf, dtype=np.float32)

    registry = ModelRegistry(
        [ModelSpec("invalid", "invalid", "invalid", 1, "invalid")],
        factories={"invalid": lambda spec: NonFiniteModel(spec, 0.0)},
    )
    service = EnsembleSearchService(
        registry=registry,
        vector_backend=SimpleBackend(),
        query_enhancer=lambda query: query,
    )

    with pytest.raises(EnsembleSearchError, match="non-finite text"):
        service.search_text("query", EnsembleSearchOptions(use_enhanced_query=False))
    with pytest.raises(EnsembleSearchError, match="non-finite image"):
        service.search_image(object(), EnsembleSearchOptions())


def test_zero_norm_query_embeddings_become_model_errors() -> None:
    class ZeroModel(FakeModel):
        def encode_texts(self, texts: list[str]) -> np.ndarray:
            return np.zeros((len(texts), 1), dtype=np.float32)

        def encode_images(self, images: list[object]) -> np.ndarray:
            return np.zeros((len(images), 1), dtype=np.float32)

    registry = ModelRegistry(
        [ModelSpec("zero", "zero", "zero", 1, "zero")],
        factories={"zero": lambda spec: ZeroModel(spec, 0.0)},
    )
    service = EnsembleSearchService(
        registry=registry,
        vector_backend=SimpleBackend(),
        query_enhancer=lambda query: query,
    )

    with pytest.raises(EnsembleSearchError, match="zero-norm.*text"):
        service.search_text("query", EnsembleSearchOptions(use_enhanced_query=False))
    with pytest.raises(EnsembleSearchError, match="zero-norm.*image"):
        service.search_image(object(), EnsembleSearchOptions())
